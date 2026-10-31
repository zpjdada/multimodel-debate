"""Private local debate console. Run: python console_server.py"""
from __future__ import annotations

import argparse
import base64
import hmac
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import debate_tools as d

ROOT = Path(__file__).resolve().parent
MAX_MATERIAL_BYTES = 20 * 1024 * 1024
MAX_REQUEST_BYTES = 30 * 1024 * 1024


def decode_materials(items):
    if not isinstance(items, list) or len(items) > 20:
        raise ValueError('最多选择20份材料，总大小不超过20MB')
    result, names, total = [], set(), 0
    for item in items:
        name = item.get('name', '')
        if (not isinstance(name, str) or not name or len(name) > 150
                or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith(('.', ' '))
                or name.startswith('.') or Path(name).suffix.lower() not in ('.pdf', '.txt', '.md', '.csv', '.json')):
            raise ValueError('材料只支持普通文件名的 PDF、TXT、MD、CSV、JSON')
        if name.casefold() in names or name.split('.')[0].upper() in {
                'CON', 'PRN', 'AUX', 'NUL', *[f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)]}:
            raise ValueError('材料文件名重复或为系统保留名称')
        try:
            content = base64.b64decode(item['base64'], validate=True)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('材料编码无效，请重新选择文件') from exc
        total += len(content)
        if total > MAX_MATERIAL_BYTES:
            raise ValueError('材料总大小不能超过20MB')
        names.add(name.casefold())
        result.append((name, content))
    return result


class Console:
    def __init__(self, root=ROOT):
        self.root = root
        self.runs = root / '.console/runs'
        self.runs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.active = None
        self.token = secrets.token_urlsafe(32)

    def folder(self, ident):
        if ident == 'current':
            return self.root
        if not re.fullmatch(r'[a-f0-9]{16}', ident):
            raise ValueError('无效场次 ID')
        path = self.runs / ident
        if not path.is_dir():
            raise ValueError('场次不存在')
        return path

    def read(self, path, default=None):
        if not path.exists():
            return default
        return d.read_json(path)

    def inventory(self):
        return sorted(d.inventory(self.root))

    def environment(self):
        cli = d.find_cli()
        result = {'python': sys.version.split()[0], 'cli': cli, 'ok': False}
        if not cli:
            return {**result, 'error': '未找到 OpenCode CLI。请安装 OpenCode 并确保 opencode 在 PATH 中，然后重启控制台。'}
        try:
            version = d.run_cli(cli, ['--version'], self.root, timeout=30)
            if version.returncode:
                raise ValueError('opencode --version 执行失败')
            return {**result, 'version': version.stdout.strip(), 'ok': True}
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            return {**result, 'error': str(exc)}

    def defaults(self):
        lock = self.read(self.root / 'roster.lock.json', {})
        return {'seats': lock.get('seats', []),
                'protocol': self.read(self.root / 'protocol.json', d.default_protocol(6)),
                'brief': (self.root / 'research_brief.md').read_text(encoding='utf-8')
                if (self.root / 'research_brief.md').exists() else '',
                'materials': [str(p.relative_to(self.root / 'materials'))
                              for p in (self.root / 'materials').rglob('*') if p.is_file()]}

    def list_runs(self):
        paths = [('current', self.root)] if (self.root / 'debate').exists() else []
        paths += [(p.name, p) for p in sorted(self.runs.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if p.is_dir()]
        result = []
        for ident, p in paths:
            info = self.read(p / 'console_run.json', {'title': '已有辩论记录（只读）', 'status': 'imported'})
            if info['status'] in ('running', 'checking') and ident != self.active:
                info['status'] = 'interrupted'
            result.append({'id': ident, **info})
        return result

    def detail(self, ident):
        p = self.folder(ident)
        info = self.read(p / 'console_run.json', {'title': '已有辩论记录（只读）', 'status': 'imported'})
        protocol = self.read(p / 'protocol.json', {})
        speeches, edges = [], []
        for f in sorted((p / 'debate').glob('round*/*.md')):
            text = f.read_text(encoding='utf-8-sig')
            try:
                meta = d.metadata(text)
            except ValueError:
                meta = {}
            speeches.append({'file': f'{f.parent.name}/{f.name}', 'text': text, 'metadata': meta})
            for response in meta.get('responses', []):
                edges.append({'from': meta.get('agent_id'), 'round': meta.get('round'), **response})
        catalog = {}
        for filename in ('candidates.json', 'conclusions.json', 'solutions.json'):
            if (p / 'debate' / filename).exists():
                catalog = self.read(p / 'debate' / filename)
        final = p / 'debate/final.md'
        log = p / 'console.log'
        tail = ''
        if log.exists():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 24000))
                tail = stream.read().decode('utf-8', errors='replace')
        status = info.get('status')
        if ident != self.active and status in ('running', 'checking'):
            status = 'interrupted'
        expected = protocol.get('rounds', 3)
        count = len(self.read(p / 'roster.lock.json', {}).get('seats', []))
        if status == 'checking':
            phase = '正在检查本场模型、Agent 与检索权限'
        elif status == 'completed':
            phase = '讨论结束，结果已保存'
        elif status == 'running':
            phase = '正在整理最终报告'
            for number in range(1, expected + 1):
                done = sum(s['metadata'].get('round') == number for s in speeches)
                if done < count:
                    phase = f'第 {number}/{expected} 轮讨论，已保存 {done}/{count} 份发言'
                    if number == expected and not (p / 'debate/packet_manifest.json').exists():
                        phase = '主持正在归并候选并冻结投票资料'
                    break
        else:
            phase = '可创建或启动讨论；运行失败详情见日志' if status != 'imported' else '历史结果（只读）'
        return {'id': ident, **info, 'status': status, 'protocol': protocol,
                'seats': self.read(p / 'roster.lock.json', {}).get('seats', []),
                'speeches': speeches, 'relations': edges, 'catalog': catalog,
                'audit': self.read(p / 'debate/audit.json', {}),
                'doctor': self.read(p / 'console_doctor.json', {}),
                'final': final.read_text(encoding='utf-8') if final.exists() else '', 'log': tail,
                'phase': phase,
                'materials': [str(f.relative_to(p / 'materials')) for f in (p / 'materials').rglob('*') if f.is_file()]}

    def create(self, data):
        title = str(data.get('title', '')).strip()
        brief = str(data.get('brief', '')).strip()
        fields = data.get('fields')
        if fields is not None:
            if not isinstance(fields, dict) or not str(fields.get('question', '')).strip():
                raise ValueError('请填写要解决的问题或具体研究目标')
            brief = '# ' + title + '\n\n' + '\n\n'.join(
                f'## {heading}\n{str(fields.get(key, "")).strip() or "未提供"}'
                for key, heading in [('question', '本场问题与期望产出'), ('background', '背景'),
                                     ('known', '已知信息与负面结论'), ('constraints', '资源、权限与验收条件')])
            extra = str(fields.get('extra', '')).strip()
            if extra:
                brief += '\n\n## 其他研究简报\n' + extra
        materials = decode_materials(data.get('materials', []))
        seats = data.get('seats', [])
        mode = data.get('mode', 'proposal')
        rounds = data.get('rounds')
        threshold = data.get('threshold')
        parallel = data.get('parallel', min(4, len(seats)))
        if not title or len(title) > 200 or not brief or len(brief) > 100000:
            raise ValueError('请填写标题及研究背景（标题≤200字，背景≤100000字）')
        if not isinstance(seats, list) or not 3 <= len(seats) <= 12:
            raise ValueError('席位数须为3–12，至少回应两个其他席位')
        if mode not in d.MODES or type(rounds) is not int or not 2 <= rounds <= 4:
            raise ValueError('模式无效或轮次不在2–4之间')
        if type(threshold) is not int or not 1 <= threshold <= len(seats):
            raise ValueError('通过票数须在1至席位总数之间')
        if type(parallel) is not int or not 1 <= parallel <= len(seats):
            raise ValueError('并发数须在1至席位总数之间')
        if sum(s.get('chair') is True for s in seats) != 1:
            raise ValueError('必须指定且只能指定一个主持')
        ids = self.inventory()
        models = list(dict.fromkeys(s.get('model') for s in seats))
        if not models or any(m not in ids for m in models):
            raise ValueError('请选择实际可用的模型 ID；允许全部席位使用同一个模型')
        mapping = {f'family_{i}': model for i, model in enumerate(models)}
        roles = []
        for i, seat in enumerate(seats):
            if not str(seat.get('role', '')).strip() or not str(seat.get('focus', '')).strip():
                raise ValueError('每个席位需要分工与研究重点')
            roles.append({'id': f'a{i+1:02d}', 'family': f'family_{models.index(seat["model"])}',
                          'role': str(seat['role'])[:200], 'focus': str(seat['focus'])[:4000],
                          **({'chair': True} if seat.get('chair') else {})})
        ident = secrets.token_hex(8)
        p = self.runs / ident
        p.mkdir()
        for name in ('debate_tools.py', 'run_debate.py'):
            shutil.copy2(self.root / name, p / name)
        for name in ('prompts', 'templates'):
            if (self.root / name).exists():
                shutil.copytree(self.root / name, p / name)
        if data.get('include_project_materials') is True and (self.root / 'materials').exists():
            shutil.copytree(self.root / 'materials', p / 'materials')
        (p / 'materials').mkdir(exist_ok=True)
        existing = {f.name.casefold() for f in (p / 'materials').iterdir()}
        for name, content in materials:
            if name.casefold() in existing:
                shutil.rmtree(p)
                raise ValueError(f'材料 {name} 与继承的项目文件重名，请取消继承或重命名后上传')
            (p / 'materials' / name).write_bytes(content)
        material_paths = [str(f.relative_to(p)).replace('\\', '/')
                          for f in (p / 'materials').rglob('*') if f.is_file()]
        if material_paths:
            brief += '\n\n## 本场材料\n' + '\n'.join(f'- `{name}`' for name in material_paths)
            brief += '\n\n请实际阅读材料并记录读取层级；未读到正文时如实注明，不以文件存在代替核读。\n'
        skills = self.root / '.opencode/skills'
        if skills.exists():
            shutil.copytree(skills, p / '.opencode/skills')
        d.atomic_json(p / 'roles.json', roles)
        d.atomic_json(p / 'protocol.json', {'mode': mode, 'rounds': rounds,
                      'threshold': {'numerator': threshold, 'denominator': len(seats)}})
        d.atomic_text(p / 'research_brief.md', brief)
        try:
            d.setup(p, ids, supplied=mapping, search=False)
        except Exception:
            shutil.rmtree(p)
            raise
        d.atomic_json(p / 'console_run.json', {'title': title, 'status': 'ready', 'parallel': parallel})
        return ident

    def start(self, ident):
        if ident == 'current':
            raise ValueError('已有项目记录只读，请新建场次')
        p = self.folder(ident)
        with self.lock:
            if self.active:
                raise ValueError('已有场次运行中，请等待完成')
            info = self.read(p / 'console_run.json')
            if info['status'] == 'completed':
                raise ValueError('场次已完成，请查看结果或新建场次')
            self.active = ident
            info.pop('error', None)
            info['status'] = 'checking'
            d.atomic_json(p / 'console_run.json', info)
            threading.Thread(target=self.worker, args=(ident,), daemon=True).start()

    def worker(self, ident):
        p = self.folder(ident)
        info = self.read(p / 'console_run.json')
        try:
            executable = d.find_cli()
            if not executable:
                raise ValueError('未找到 OpenCode CLI')
            # Run in the isolated workspace, including the actual runtime doctor.
            with (p / 'console.log').open('a', encoding='utf-8') as log:
                check = subprocess.run([sys.executable, '-X', 'utf8', 'debate_tools.py', 'doctor'],
                                       cwd=p, text=True, encoding='utf-8', capture_output=True, timeout=180)
                log.write(check.stdout + check.stderr)
                log.flush()
                doctor = json.loads(check.stdout)
                d.atomic_json(p / 'console_doctor.json', doctor)
                if check.returncode or not doctor.get('ok'):
                    raise ValueError('doctor 未通过，请查看检查结果')
                info['status'] = 'running'
                d.atomic_json(p / 'console_run.json', info)
                result = subprocess.run([sys.executable, '-X', 'utf8', '-u', 'run_debate.py',
                                         'all', '--resume', '--parallel', str(info['parallel'])],
                                        cwd=p, stdout=log, stderr=subprocess.STDOUT)
            info['status'] = 'completed' if result.returncode == 0 else 'failed'
            info['exit_code'] = result.returncode
        except Exception as exc:
            info['status'], info['error'] = 'failed', str(exc)
        finally:
            d.atomic_json(p / 'console_run.json', info)
            with self.lock:
                self.active = None


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, value, status=200, content_type='application/json; charset=utf-8'):
            payload = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def authenticated(self):
            return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + app.token)

        def do_GET(self):
            path = urlparse(self.path).path
            static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                      '/style.css': ('style.css', 'text/css'), '/launcher.css': ('launcher.css', 'text/css')}
            if path in static:
                name, mime = static[path]
                return self.send((ROOT / 'console_web' / name).read_bytes(), content_type=mime + '; charset=utf-8')
            if not self.authenticated():
                return self.send({'error': '请使用启动地址中的访问凭证登录'}, 401)
            try:
                if path == '/api/environment':
                    result = app.environment()
                elif path == '/api/models':
                    result = {'models': app.inventory()}
                elif path == '/api/defaults':
                    result = app.defaults()
                elif path == '/api/runs':
                    result = app.list_runs()
                elif path.startswith('/api/runs/'):
                    result = app.detail(path.removeprefix('/api/runs/'))
                else:
                    return self.send({'error': 'Not found'}, 404)
                self.send(result)
            except Exception as exc:
                self.send({'error': str(exc)}, 400)

        def do_POST(self):
            if not self.authenticated():
                return self.send({'error': '未授权'}, 401)
            # Cross-origin browser requests cannot use this API.
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.send({'error': '跨源请求被拒绝'}, 403)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_REQUEST_BYTES:
                    raise ValueError('请求体大小无效')
                data = json.loads(self.rfile.read(size))
                path = urlparse(self.path).path
                if path == '/api/runs':
                    self.send({'id': app.create(data)}, 201)
                elif re.fullmatch(r'/api/runs/[a-f0-9]{16}/start', path):
                    app.start(path.split('/')[3])
                    self.send({'ok': True}, 202)
                else:
                    self.send({'error': 'Not found'}, 404)
            except Exception as exc:
                self.send({'error': str(exc)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true', help='Open the local console in your browser')
    args = parser.parse_args()
    app = Console()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(app))
    url = f'http://127.0.0.1:{server.server_port}/#token={app.token}'
    print(f'Private console: {url}', flush=True)
    print('Keep this process running. Access token is local and changes on restart.', flush=True)
    if args.open:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    server.serve_forever()


if __name__ == '__main__':
    main()

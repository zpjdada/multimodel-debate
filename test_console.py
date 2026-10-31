"""Offline API/integration tests; no paid model calls."""
import json
import base64
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

import console_server as c
import debate_tools as d


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for file in ('debate_tools.py', 'run_debate.py'):
            shutil.copy(c.ROOT / file, self.root / file)
        for folder in ('prompts', 'templates'):
            shutil.copytree(c.ROOT / folder, self.root / folder)
        self.app = c.Console(self.root)
        self.inventory = patch.object(self.app, 'inventory', return_value=['mock/one', 'mock/two'])
        self.inventory.start()
        self.addCleanup(self.inventory.stop)
        self.payload = {'title': 'Synthetic test', 'brief': 'Synthetic research only', 'mode': 'proposal',
                        'rounds': 3, 'threshold': 3, 'parallel': 2,
                        'seats': [{'model': 'mock/one' if i < 2 else 'mock/two', 'role': 'Test',
                                   'focus': 'Synthetic focus', 'chair': i == 1} for i in range(3)]}

    def test_isolated_config_and_real_record_projection(self):
        ident = self.app.create(self.payload)
        folder = self.app.folder(ident)
        self.assertFalse((self.root / 'opencode.json').exists())
        lock = d.read_json(folder / 'roster.lock.json')
        self.assertEqual(lock['seats'][1]['agent_name'], 'debate-chair')
        self.assertEqual(lock['seats'][0]['model'], 'mock/one')
        meta = {'agent_id': 'a01', 'round': 2, 'responses': [
            {'to_agent': 'a02', 'stance': 'oppose', 'claim': '<script>not executable</script>'}]}
        d.atomic_text(folder / 'debate/round2/a01.md', 'Synthetic\n```json\n'+json.dumps(meta)+'\n```')
        result = self.app.detail(ident)
        self.assertEqual(result['relations'][0]['to_agent'], 'a02')
        self.assertEqual(len(result['speeches']), 1)
        self.assertEqual(self.app.list_runs()[0]['id'], ident)

    def test_structured_brief_and_uploaded_materials_are_isolated(self):
        (self.root / 'materials').mkdir()
        (self.root / 'materials/private.txt').write_text('Old topic', encoding='utf-8')
        self.payload['fields'] = {'question': 'How to test?', 'background': 'Synthetic background',
                                  'known': 'No results', 'constraints': 'Offline only'}
        self.payload['materials'] = [{'name': '研究笔记.md', 'base64': base64.b64encode(b'Synthetic note').decode()}]
        ident = self.app.create(self.payload)
        folder = self.app.folder(ident)
        brief = (folder / 'research_brief.md').read_text(encoding='utf-8')
        self.assertIn('How to test?', brief)
        self.assertIn('materials/研究笔记.md', brief)
        self.assertEqual((folder / 'materials/研究笔记.md').read_bytes(), b'Synthetic note')
        self.assertFalse((folder / 'materials/private.txt').exists())
        self.payload['include_project_materials'] = True
        another = self.app.folder(self.app.create(self.payload))
        self.assertTrue((another / 'materials/private.txt').exists())

    def test_invalid_material_does_not_create_workspace(self):
        for name in ('../escape.md', 'C:\\evil.pdf', 'CON.txt', '.env', 'payload.exe'):
            with self.subTest(name=name):
                self.payload['materials'] = [{'name': name, 'base64': 'dGVzdA=='}]
                with self.assertRaises(ValueError):
                    self.app.create(self.payload)
        self.assertEqual(list(self.app.runs.iterdir()), [])
        with self.assertRaises(ValueError):
            c.decode_materials([{'name': 'note.txt', 'base64': '!!!'}])

    def test_environment_failure_is_actionable(self):
        with patch.object(d, 'find_cli', return_value=None):
            state = self.app.environment()
        self.assertFalse(state['ok'])
        self.assertIn('PATH', state['error'])

    def test_invalid_seats_and_paths_rejected(self):
        self.payload['seats'][0]['chair'] = True
        with self.assertRaises(ValueError):
            self.app.create(self.payload)
        for ident in ('../', '..\\', 'current/../../'):
            with self.assertRaises(ValueError):
                self.app.folder(ident)

    def test_all_seats_can_use_one_model_and_parallelism_is_automatic(self):
        self.payload.pop('parallel')
        for seat in self.payload['seats']:
            seat['model'] = 'mock/one'
        ident = self.app.create(self.payload)
        folder = self.app.folder(ident)
        lock = d.read_json(folder / 'roster.lock.json')
        self.assertEqual(len(lock['seats']), 3)
        self.assertEqual({r['model'] for r in lock['seats']}, {'mock/one'})
        self.assertEqual(len({r['agent_name'] for r in lock['seats']}), 3)
        self.assertEqual(self.app.detail(ident)['parallel'], 3)

        self.payload['seats'] += [dict(self.payload['seats'][0], chair=False) for _ in range(3)]
        self.payload['threshold'] = 5
        six = self.app.detail(self.app.create(self.payload))
        self.assertEqual(len(six['seats']), 6)
        self.assertEqual(six['parallel'], 4)

    def test_worker_gates_driver_on_doctor(self):
        ident = self.app.create(self.payload)
        self.app.active = ident
        with patch.object(d, 'find_cli', return_value='mock'), patch.object(subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 1, json.dumps({'ok': False}), '')
            self.app.worker(ident)
            self.assertEqual(run.call_count, 1)
        self.assertEqual(self.app.detail(ident)['status'], 'failed')
        self.assertIsNone(self.app.active)

    def test_worker_invokes_resume_driver_with_selected_parallelism(self):
        ident = self.app.create(self.payload)
        with patch.object(d, 'find_cli', return_value='mock'), patch.object(subprocess, 'run') as run:
            run.side_effect = [subprocess.CompletedProcess([], 0, json.dumps({'ok': True}), ''),
                               subprocess.CompletedProcess([], 0)]
            self.app.worker(ident)
            args = run.call_args_list[1].args[0]
            self.assertEqual(args[-4:], ['all', '--resume', '--parallel', '2'])
            self.assertEqual(run.call_args.kwargs['cwd'], self.app.folder(ident))
        self.assertEqual(self.app.detail(ident)['status'], 'completed')

    def test_http_auth_origin_and_create(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), c.handler_for(self.app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:'+str(server.server_port)
        with self.assertRaises(HTTPError) as err:
            urlopen(base+'/api/runs')
        self.assertEqual(err.exception.code, 401)
        err.exception.close()
        headers = {'Authorization': 'Bearer '+self.app.token, 'Content-Type': 'application/json'}
        body = json.dumps(self.payload).encode()
        with self.assertRaises(HTTPError) as err:
            urlopen(Request(base+'/api/runs', body, {**headers, 'Origin':'https://other.invalid'}))
        self.assertEqual(err.exception.code, 403)
        err.exception.close()
        with urlopen(Request(base+'/api/runs', body, headers)) as response:
            self.assertEqual(response.status, 201)
            ident = json.load(response)['id']
        with urlopen(Request(base+'/api/runs/'+ident, headers=headers)) as response:
            self.assertEqual(json.load(response)['status'], 'ready')


if __name__ == '__main__':
    unittest.main()

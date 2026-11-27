#!/usr/bin/env python3
"""
render_debug.py -- CLI for inspecting and patching a live FLA app's database.

The target app must have DEBUG_SECRET set and the debug_routes blueprint registered.

Usage:
    python3 render_debug.py --url https://fiat-lux.onrender.com --secret <SECRET> <command>

Commands:
    list                        List all files in the DB (id, name, type, updated)
    viz  <file_id>              Print a file's visualization HTML to stdout
    chat <file_id>              Print a file's chat history as JSON
    save-viz <file_id> <path>   Save visualization HTML to a local file
    put-viz  <file_id> <path>   Replace a file's visualization with the contents of <path>

Environment:
    RENDER_DEBUG_URL     Default app URL (overridden by --url)
    RENDER_DEBUG_SECRET  Default secret   (overridden by --secret)

Example workflow to fix a visualization:
    # 1. Download the broken viz
    python3 render_debug.py viz abc123 > /tmp/viz.html

    # 2. Edit /tmp/viz.html locally

    # 3. Push the fix back
    python3 render_debug.py put-viz abc123 /tmp/viz.html
"""

import argparse
import json
import os
import sys
import requests


def _base(url: str) -> str:
    return url.rstrip('/') + '/debug'


def _headers(secret: str) -> dict:
    return {'Authorization': f'Bearer {secret}'}


def cmd_list(url: str, secret: str, **_):
    r = requests.get(f'{_base(url)}/files', headers=_headers(secret), timeout=15)
    r.raise_for_status()
    files = r.json()
    if not files:
        print('No files found.')
        return
    fmt = '{:<36}  {:<8}  {:<10}  {}'
    print(fmt.format('ID', 'TYPE', 'UPDATED', 'NAME'))
    print('-' * 80)
    for f in files:
        print(fmt.format(
            f['id'],
            (f['file_type'] or '')[:8],
            (f['updated_at'] or '')[:10],
            f['display_name'],
        ))


def cmd_viz(url: str, secret: str, file_id: str, **_):
    r = requests.get(f'{_base(url)}/viz/{file_id}', headers=_headers(secret), timeout=15)
    r.raise_for_status()
    data = r.json()
    viz = data.get('visualization') or ''
    print(viz, end='')


def cmd_chat(url: str, secret: str, file_id: str, **_):
    r = requests.get(f'{_base(url)}/chat/{file_id}', headers=_headers(secret), timeout=15)
    r.raise_for_status()
    data = r.json()
    print(json.dumps(data['chat_history'], indent=2))


def cmd_save_viz(url: str, secret: str, file_id: str, path: str, **_):
    r = requests.get(f'{_base(url)}/viz/{file_id}', headers=_headers(secret), timeout=15)
    r.raise_for_status()
    viz = r.json().get('visualization') or ''
    with open(path, 'w') as f:
        f.write(viz)
    print(f'Saved {len(viz)} bytes to {path}')


def cmd_put_viz(url: str, secret: str, file_id: str, path: str, **_):
    with open(path) as f:
        viz = f.read()
    r = requests.post(
        f'{_base(url)}/set-viz/{file_id}',
        headers={**_headers(secret), 'Content-Type': 'application/json'},
        json={'visualization': viz},
        timeout=15,
    )
    r.raise_for_status()
    print(f'Updated visualization for {file_id} ({len(viz)} bytes)')


COMMANDS = {
    'list':     (cmd_list,     []),
    'viz':      (cmd_viz,      ['file_id']),
    'chat':     (cmd_chat,     ['file_id']),
    'save-viz': (cmd_save_viz, ['file_id', 'path']),
    'put-viz':  (cmd_put_viz,  ['file_id', 'path']),
}


def main():
    parser = argparse.ArgumentParser(description='Debug a live FLA app via its /debug endpoints.')
    parser.add_argument('--url', default=os.environ.get('RENDER_DEBUG_URL', ''), help='App base URL')
    parser.add_argument('--secret', default=os.environ.get('RENDER_DEBUG_SECRET', ''), help='DEBUG_SECRET value')
    parser.add_argument('command', choices=list(COMMANDS))
    parser.add_argument('args', nargs='*', help='Command arguments')
    opts = parser.parse_args()

    if not opts.url:
        sys.exit('Error: --url is required (or set RENDER_DEBUG_URL)')
    if not opts.secret:
        sys.exit('Error: --secret is required (or set RENDER_DEBUG_SECRET)')

    fn, arg_names = COMMANDS[opts.command]
    if len(opts.args) < len(arg_names):
        sys.exit(f'Error: {opts.command} requires: {" ".join(arg_names)}')

    kwargs = dict(url=opts.url, secret=opts.secret)
    for name, val in zip(arg_names, opts.args):
        kwargs[name] = val

    try:
        fn(**kwargs)
    except requests.HTTPError as e:
        sys.exit(f'HTTP error: {e.response.status_code} {e.response.text}')


if __name__ == '__main__':
    main()

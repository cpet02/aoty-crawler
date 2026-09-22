#!/usr/bin/env python3
"""Launch the Radius UI: python ui/launch.py [--port 8501]

A thin wrapper around `streamlit run ui/app.py` that sets the environment
the app needs regardless of where it is started from.
"""

import argparse
import os
import subprocess
import sys

# Windows consoles that default to a legacy codepage choke on the album
# titles this app prints; force UTF-8 where the runtime supports it.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description='Launch the Radius UI.')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--headless', action='store_true',
                        help='Do not open a browser tab automatically.')
    args = parser.parse_args(argv)

    ui_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(ui_dir)
    app_path = os.path.join(ui_dir, 'app.py')

    env = os.environ.copy()
    # Let `import radius` work no matter where streamlit is launched from.
    env['PYTHONPATH'] = project_root + os.pathsep + env.get('PYTHONPATH', '')
    env['PYTHONIOENCODING'] = 'utf-8'
    # pandas pulls in OpenBLAS, which tries to allocate one large buffer per
    # CPU thread at import time and dies on machines that are short of
    # commit memory. One thread is plenty for a results table.
    env.setdefault('OPENBLAS_NUM_THREADS', '1')
    env.setdefault('STREAMLIT_BROWSER_GATHER_USAGE_STATS', 'false')

    command = [sys.executable, '-m', 'streamlit', 'run', app_path,
               '--server.port', str(args.port)]
    if args.headless:
        command += ['--server.headless', 'true']

    print(f'Radius UI: http://localhost:{args.port}  (Ctrl+C to stop)')
    return subprocess.call(command, cwd=project_root, env=env)


if __name__ == '__main__':
    sys.exit(main())

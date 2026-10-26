"""Build and validate an immutable release with Blender's native extension tools."""
import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path,
                        help='New, empty directory for the package and index.json')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Output directory must be empty; previous releases are immutable')
    output.mkdir(parents=True, exist_ok=True)
    # Keep test preferences separate from the normal Blender installation.
    profile = output.parent / (output.name + '-test-profile')
    env = os.environ.copy()
    env['BLENDER_USER_CONFIG'] = str(profile / 'config')
    env['BLENDER_USER_SCRIPTS'] = str(profile / 'scripts')
    env['BLENDER_USER_EXTENSIONS'] = str(profile / 'extensions')
    base = [str(args.blender.resolve()), '--background', '--factory-startup']

    def run(*arguments):
        subprocess.run(base + list(arguments), check=True, env=env)

    run('--disable-autoexec', '--python-exit-code', '1', '--python',
        str(source / 'tests' / 'test_blender.py'))
    run('--command', 'extension', 'build', '--source-dir', str(source),
        '--output-dir', str(output))
    archives = list(output.glob('*.zip'))
    if len(archives) != 1:
        raise RuntimeError('Expected exactly one built extension')
    run('--command', 'extension', 'validate', str(archives[0]))
    run('--command', 'extension', 'server-generate', '--repo-dir', str(output))
    print(f'Release prepared: {output}')


if __name__ == '__main__':
    main()

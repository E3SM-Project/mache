from pathlib import Path


def post_pixi(ctx):
    if getattr(ctx.args, 'with_albany', False):
        marker = Path(ctx.work_dir) / 'with_albany.txt'
        marker.write_text('enabled\n', encoding='utf-8')

    moab_version = getattr(ctx.args, 'moab_version', None)
    if moab_version:
        marker = Path(ctx.work_dir) / 'moab_version.txt'
        marker.write_text(f'{moab_version}\n', encoding='utf-8')

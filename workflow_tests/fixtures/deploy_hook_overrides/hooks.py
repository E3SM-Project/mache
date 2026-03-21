from pathlib import Path


def post_pixi(ctx):
    if getattr(ctx.args, 'with_albany', False):
        marker = Path(ctx.work_dir) / 'with_albany.txt'
        marker.write_text('enabled\n', encoding='utf-8')

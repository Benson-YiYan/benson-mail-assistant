"""Local CommonMark renderer with tables, no raw HTML or remote images."""
import sys
from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml

def render(text):
    lines = text.splitlines()
    if lines and lines[0].startswith('邮件编号：'):
        lines.pop(0)
        if lines and lines[0].startswith('邮箱标识：'):
            lines.pop(0)
    parser = MarkdownIt('commonmark', {'html': False}).enable('table').enable('strikethrough')
    parser.renderer.rules['image'] = lambda tokens, index, options, env: '<span>' + escapeHtml(tokens[index].content) + '</span>'
    return parser.render('\n'.join(lines))

if __name__ == '__main__':
    print(render(sys.stdin.read()), end='')

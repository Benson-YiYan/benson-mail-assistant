import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Runtime'))
from markdown_render import render

class MarkdownRenderingTests(unittest.TestCase):
    def test_commonmark_blocks_and_inline_literals(self):
        html=render('## Heading\n\n3. First\n   - Nested **bold**\n4. Second\n\n`**literal**`\n\n| A | B |\n| --- | --- |\n| C | D |\n\n```text\n**code**\n```')
        self.assertIn('<h2>Heading</h2>',html)
        self.assertIn('<ol start="3">',html)
        self.assertIn('<ul>\n<li>Nested <strong>bold</strong></li>',html)
        self.assertIn('<code>**literal**</code>',html)
        self.assertIn('<td>C</td>',html)
        self.assertIn('<pre><code class="language-text">**code**',html)

    def test_untrusted_html_links_and_images_remain_inert(self):
        html=render('<script>alert(1)</script>\n\n![remote](https://example.invalid/track)\n\n[bad](javascript:alert(1))\n\n[good](https://example.invalid)')
        self.assertNotIn('<script',html)
        self.assertNotIn('<img',html)
        self.assertNotIn('href="javascript:',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('href="https://example.invalid"',html)

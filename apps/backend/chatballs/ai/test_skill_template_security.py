from django.test import SimpleTestCase

from chatballs.ai.skill_templates.engine import compile_template, render_template
from chatballs.ai.skill_templates.errors import TemplateError
from chatballs.ai.skill_templates.order_basis import order_basis


class TemplateSecurityTests(SimpleTestCase):
    def setUp(self):
        self.template = order_basis(language="ru")["templates"][1]
        self.data = self.template["examples"][0]

    def test_positive_html_policy_rejects_active_or_resource_markup(self):
        for html in (
            '<script>alert(1)</script>', '<div onclick="alert(1)">x</div>',
            '<img src="https://evil.test/x">', '<iframe srcdoc="x"></iframe>',
            '<form><input name="x"></form>', '<object data="x"></object>',
            '<style>body{color:red}</style>', '<link rel="stylesheet" href="https://evil.test">',
            '<video src="x"></video>', '<meta http-equiv="refresh" content="0">',
            '<div style="color:red">x</div>', '<div id="shell">x</div>',
            '<svg><foreignObject><p>x</p></foreignObject></svg>',
            '<svg><use href="https://evil.test/x"></use></svg>',
            '<svg><animate attributeName="href"></animate></svg>',
            '<svg onload="alert(1)"></svg>', '<!--{{order_no}}-->',
            '<p><div>broken</div></p>', '<math><mtext>x</mtext></math>',
            '<{{order_no}}>x</{{order_no}}>', '<span {{order_no}}="x">x</span>',
            '<div>{{#if eta}}x</div>{{/if}}',
            '<{{#if eta}}div{{/if}}>x</div>',
            '<p title={{order_no}}>x</p>',
            '<p class="{{#if eta}}active{{/if}}">x</p>',
            '<a href="skillvalue">relative</a>',
        ):
            with self.subTest(html=html), self.assertRaises(TemplateError):
                compile_template({**self.template, "html": html})

    def test_context_escaping_and_final_policy_block_xss_and_dangerous_uri(self):
        malicious = '<img src=x onerror="alert(1)">&\'"'
        template = {**self.template, "html": '<p title="{{order_no}}">{{order_no}}</p>'}
        result = render_template(template, {**self.data, "order_no": malicious}, language="ru")
        self.assertIn("&lt;img", result["contentHtml"])
        self.assertNotIn("<img", result["contentHtml"])
        self.assertNotIn('<script', result["presentation"]["srcDoc"])
        self.assertIn(malicious, result["text"])
        template = {**self.template, "html": '<a href="{{order_no}}">{{status}}</a>'}
        for uri in ("javascript:alert(1)", "data:text/html,x", "vbscript:foo", "//evil.test",
                    "/relative", "https://user:pass@evil.test", "https://evil.test\\@good.test",
                    "java\nscript:alert(1)", "https://evil.test/\x01", "http://[invalid"):
            with self.subTest(uri=uri), self.assertRaises(TemplateError) as error:
                render_template(template, {**self.data, "order_no": uri}, language="ru", origin="example")
            self.assertEqual(error.exception.detail["origin"], "example")
        result = render_template(template, {**self.data, "order_no": "https://example.test/a?q=1&b=2"}, language="ru")
        self.assertIn('rel="noopener noreferrer"', result["contentHtml"])
        self.assertIn('referrerpolicy="no-referrer"', result["contentHtml"])
        for uri in ("javascript&#58;alert(1)", "&#106;avascript:alert(1)"):
            with self.assertRaises(TemplateError):
                compile_template({**self.template, "html": f'<a href="{uri}">x</a>'})

    def test_css_parser_rejects_resources_escapes_injection_and_shell_effects(self):
        for css in (
            '@import "https://evil.test/x";', '@font-face{font-family:x;src:url(x)}',
            '.x{background:url(https://evil.test)}', r'.x{background:u\72l(https://evil.test)}',
            '.x{background:image-set("https://evil.test" 1x)}',
            '.x{color:expression(alert(1))}', '.x{behavior:url(x)}',
            '.x{position:fixed}', '.x{z-index:9999}', '.x{--x:red}',
            '.x{color:var(--shell-color)}', '.x{width:100vw}', '.x{margin:-10px}',
            '.x{color:red!important}', '.x{color:red', '</style><script>alert(1)</script>',
            '.x{color:attr(data-x)}', '.x{content:"</style>"}',
        ):
            with self.subTest(css=css), self.assertRaises(TemplateError):
                compile_template({**self.template, "css": css})
        # A broad selector stays inside its isolated document. It cannot reach
        # the shell, even when it is syntactically valid CSS.
        result = render_template({**self.template, "css": 'body{background:red}'}, self.data, language="ru")
        self.assertEqual(result["presentation"]["isolation"], "sandboxed-iframe")
        self.assertEqual(result["presentation"]["sandbox"], "")
        self.assertIn("form-action &#x27;none&#x27;", result["presentation"]["srcDoc"])

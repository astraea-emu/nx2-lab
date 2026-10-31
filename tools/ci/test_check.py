"""Repository-file link checks stay offline and ignore generated/code examples."""
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

from check import check_markdown_links


class MarkdownLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write(self, name, content=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            check_markdown_links(self.root)

    def test_relative_files_images_references_and_directory_targets(self):
        self.write("README.md")
        self.write("image one.png")
        self.write("docs/start.md", """[read
the guide](../README.md#build-and-run)
![image](../image%20one.png)
[directory](../docs/)
[reference]: <../image one.png> "optional title"
""")
        self.check()

    def test_missing_inline_image_and_reference_targets_fail(self):
        for content in ("[broken](missing.md)", "![image](missing.png)",
                        "[reference]: missing.md"):
            with self.subTest(content=content):
                self.write("README.md", content)
                with self.assertRaisesRegex(ValueError, "README.md: missing"):
                    self.check()

    def test_code_urls_and_fragment_only_links_are_not_file_checks(self):
        self.write("README.md", """[web](https://example.test/missing)
[mail](mailto:missing@example.test) [anchor](#not-validated)
`[code](missing.md)`
````markdown
[code](missing.md)
```
[still code](missing.md)
````
~~~markdown
[code](missing.md)
~~~
""")
        self.check()

    def test_link_outside_repository_is_not_portable(self):
        self.write("README.md", "[outside](../outside.md)")
        with self.assertRaisesRegex(ValueError, "missing repository target"):
            self.check()

    def test_ignored_generated_markdown_is_not_scanned(self):
        self.write(".gitignore", "build/\n")
        self.write("README.md", "[local](docs/guide.md)")
        self.write("docs/guide.md")
        self.write("build/generated.md", "[broken](missing.md)")
        self.check()


if __name__ == "__main__":
    unittest.main()

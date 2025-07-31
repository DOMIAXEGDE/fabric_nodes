# fabric_nodes
A Python Programming Lab for Advanced Programmers

## Executors via entry points

Language executors are discovered from the `fabric_nodes.executors` entry point group.
A plugin can register itself by exposing a `register` function:

```python
# my_exec.py

def register(reg):
    reg.register("my_lang", run_code)
```

and declaring the entry point in its `pyproject.toml`:

```toml
[project.entry-points."fabric_nodes.executors"]
my_lang = "mypkg.my_exec"
```

After installing the package, the new language will appear in the dropdown at runtime.

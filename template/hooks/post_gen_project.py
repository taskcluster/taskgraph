from pathlib import Path

tc_yml = Path("taskcluster.{{cookiecutter.repo_host}}.yml")
tc_yml.rename(".taskcluster.yml")

proj = Path.cwd()
for unused in proj.glob("taskcluster.*.yml"):
    unused.unlink()

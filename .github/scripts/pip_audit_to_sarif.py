"""
Convert pip-audit JSON output to SARIF 2.1.0 for GitHub code scanning.

pip-audit has no SARIF output of its own. Each vulnerable package becomes
one result per advisory, located on the line of the requirements file that
pins it.

    python pip_audit_to_sarif.py <pip-audit.json> <requirements.txt> <level> <out.sarif>

<level> is the SARIF level for every result: "error" for dependencies that
ship in the image, "warning" for development-only ones.
"""
import json
import re
import sys
from pathlib import Path


def requirement_lines(path):
    """Map normalised package name -> 1-based line number in a requirements file."""
    lines = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        match = re.match(r'\s*([A-Za-z0-9][A-Za-z0-9._-]*)', line)
        if match and not line.lstrip().startswith(('#', '-')):
            lines[normalise(match.group(1))] = number
    return lines


def normalise(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def main(report_path, requirements_path, level, out_path):
    report = json.loads(Path(report_path).read_text())
    dependencies = report.get('dependencies', report if isinstance(report, list) else [])
    lines = requirement_lines(requirements_path)

    rules, results = {}, []
    for dep in dependencies:
        for vuln in dep.get('vulns', []):
            rule_id = vuln['id']
            aliases = [a for a in vuln.get('aliases', []) if a != rule_id]
            fixes = ', '.join(vuln.get('fix_versions', [])) or 'no fixed version yet'
            title = f"{dep['name']} {dep['version']} is affected by {rule_id}"
            rules.setdefault(rule_id, {
                'id': rule_id,
                'name': 'VulnerableDependency',
                'shortDescription': {'text': f"Vulnerable Python dependency ({rule_id})"},
                'fullDescription': {'text': vuln.get('description') or title},
                'helpUri': f"https://osv.dev/vulnerability/{rule_id}",
                'help': {'text': f"Upgrade to a fixed version: {fixes}. Aliases: {', '.join(aliases) or 'none'}."},
                'properties': {'tags': ['security', 'dependency', 'python']},
            })
            results.append({
                'ruleId': rule_id,
                'level': level,
                'message': {'text': f"{title}. Fixed in: {fixes}."},
                'locations': [{
                    'physicalLocation': {
                        'artifactLocation': {'uri': requirements_path},
                        'region': {'startLine': lines.get(normalise(dep['name']), 1)},
                    },
                }],
                'partialFingerprints': {'package/advisory': f"{normalise(dep['name'])}/{rule_id}"},
            })

    sarif = {
        '$schema': 'https://json.schemastore.org/sarif-2.1.0.json',
        'version': '2.1.0',
        'runs': [{
            'tool': {'driver': {
                'name': 'pip-audit',
                'informationUri': 'https://github.com/pypa/pip-audit',
                'rules': list(rules.values()),
            }},
            'results': results,
        }],
    }
    Path(out_path).write_text(json.dumps(sarif, indent=2))
    print(f"{len(results)} finding(s) from {requirements_path} written to {out_path}")


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[3] not in ('error', 'warning', 'note'):
        sys.exit(__doc__)
    main(*sys.argv[1:])

import os
import csv
import io
from typing import Dict, List
from app.models.domain import Commit

class ReportingService:
    """Generates formatted reports (Markdown, HTML, CSV) summarizing daily developer activity."""

    @staticmethod
    def generate_markdown(commits_by_feature: Dict[str, List[Commit]], date_str: str) -> str:
        """Generates a Markdown report summarizing today's commits grouped by Redmine Feature."""
        md = f"# Daily Development Update - {date_str}\n\n"
        if not commits_by_feature:
            md += "*No commits recorded for this day.*\n"
            return md

        for feature_name, commits in commits_by_feature.items():
            md += f"## Feature: {feature_name}\n\n"
            
            # Group by repository within the feature
            repo_groups: Dict[str, List[Commit]] = {}
            for c in commits:
                repo_groups.setdefault(c.repository, []).append(c)
                
            for repo, r_commits in repo_groups.items():
                md += f"### Repository: `{repo}`\n\n"
                md += "**Commits:**\n"
                for c in r_commits:
                    md += f"- {c.message}\n"
                md += "\n"
                
                md += "| Commit Hash | Commit Time | URL |\n"
                md += "| :--- | :--- | :--- |\n"
                for c in r_commits:
                    short_hash = c.hash[:8]
                    time_str = c.committed_date.strftime("%H:%M:%S")
                    url_str = f"[Link]({c.url})" if c.url else "N/A"
                    md += f"| `{short_hash}` | {time_str} | {url_str} |\n"
                md += "\n"
                
            md += "---\n\n"
        return md

    @staticmethod
    def generate_html(commits_by_feature: Dict[str, List[Commit]], date_str: str) -> str:
        """Generates a stylish, premium HTML report detailing today's commits."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Daily Work Summary - {date_str}</title>
    <style>
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #0f172a;
            color: #e2e8f0;
            line-height: 1.6;
            padding: 40px 20px;
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            color: #f8fafc;
            border-bottom: 2px solid #334155;
            padding-bottom: 12px;
            font-size: 2.2rem;
        }}
        h2 {{
            color: #38bdf8;
            margin-top: 40px;
            font-size: 1.6rem;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 6px;
        }}
        h3 {{
            color: #818cf8;
            font-size: 1.2rem;
            margin-top: 20px;
        }}
        .commit-card {{
            background: #1e293b;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 24px;
            border-left: 4px solid #4f46e5;
        }}
        ul {{
            margin: 8px 0;
            padding-left: 20px;
        }}
        li {{
            margin-bottom: 6px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            font-size: 0.9rem;
        }}
        th, td {{
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid #334155;
        }}
        th {{
            background-color: #0f172a;
            color: #94a3b8;
            font-weight: 600;
        }}
        code {{
            background-color: #0f172a;
            padding: 2px 6px;
            border-radius: 4px;
            color: #f43f5e;
            font-family: monospace;
        }}
        a {{
            color: #38bdf8;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .footer {{
            margin-top: 60px;
            text-align: center;
            font-size: 0.8rem;
            color: #64748b;
        }}
    </style>
</head>
<body>
    <h1>Daily Development Update - {date_str}</h1>
"""
        if not commits_by_feature:
            html += "<p>No commits recorded for this day.</p>"
        else:
            for feature_name, commits in commits_by_feature.items():
                html += f"<h2>Feature: {feature_name}</h2>"
                
                # Group by repository
                repo_groups: Dict[str, List[Commit]] = {}
                for c in commits:
                    repo_groups.setdefault(c.repository, []).append(c)
                    
                for repo, r_commits in repo_groups.items():
                    html += f"<div class='commit-card'>"
                    html += f"<h3>Repository: <code>{repo}</code></h3>"
                    html += "<strong>Commits:</strong>"
                    html += "<ul>"
                    for c in r_commits:
                        html += f"<li>{c.message}</li>"
                    html += "</ul>"
                    
                    html += "<table>"
                    html += "<thead><tr><th>Commit Hash</th><th>Commit Time</th><th>URL</th></tr></thead>"
                    html += "<tbody>"
                    for c in r_commits:
                        short_hash = c.hash[:8]
                        time_str = c.committed_date.strftime("%H:%M:%S")
                        url_str = f"<a href='{c.url}' target='_blank'>View Commit</a>" if c.url else "N/A"
                        html += f"<tr><td><code>{short_hash}</code></td><td>{time_str}</td><td>{url_str}</td></tr>"
                    html += "</tbody></table>"
                    html += "</div>"
                    
        html += f"""
    <div class="footer">
        Generated by CommitFlow Worklog Automator &bull; {date_str}
    </div>
</body>
</html>
"""
        return html

    @staticmethod
    def generate_csv(commits_by_feature: Dict[str, List[Commit]], date_str: str) -> str:
        """Generates a CSV report summarizing the daily developer log."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(["Date", "Feature", "Repository", "Commit Hash", "Commit Time", "Commit Message", "URL"])
        
        for feature_name, commits in commits_by_feature.items():
            for c in commits:
                time_str = c.committed_date.strftime("%H:%M:%S")
                writer.writerow([
                    date_str,
                    feature_name,
                    c.repository,
                    c.hash,
                    time_str,
                    c.message,
                    c.url or ""
                ])
                
        return output.getvalue()

    def export_reports(self, commits_by_feature: Dict[str, List[Commit]], date_str: str, output_dir: str = "reports") -> Dict[str, str]:
        """Generates and writes Markdown, HTML, and CSV reports to the filesystem."""
        os.makedirs(output_dir, exist_ok=True)
        
        md_content = self.generate_markdown(commits_by_feature, date_str)
        html_content = self.generate_html(commits_by_feature, date_str)
        csv_content = self.generate_csv(commits_by_feature, date_str)
        
        paths = {
            "markdown": os.path.join(output_dir, f"report_{date_str}.md"),
            "html": os.path.join(output_dir, f"report_{date_str}.html"),
            "csv": os.path.join(output_dir, f"report_{date_str}.csv")
        }
        
        with open(paths["markdown"], "w", encoding="utf-8") as f:
            f.write(md_content)
        with open(paths["html"], "w", encoding="utf-8") as f:
            f.write(html_content)
        with open(paths["csv"], "w", encoding="utf-8") as f:
            f.write(csv_content)
            
        return paths

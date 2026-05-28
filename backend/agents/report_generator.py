"""
Stage 5: Report Generator
Creates PDF, HTML, and JSON reports.
Uses templates for formatting, then LLM to write the executive narrative.
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from jinja2 import Template
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from .base import BaseAgent
from .guardrail import guardrail
from config import settings


class ReportGenerator(BaseAgent):
    """Generates executive, technical, and data reports with AI narrative"""
    
    def __init__(self):
        super().__init__("ReportGenerator")
        self.reports_dir = Path(__file__).parent.parent.parent / "reports"
        self.reports_dir.mkdir(exist_ok=True)
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0.2,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate three report formats
        
        Input: {
            "anomalies": List[anomaly_dict],
            "hypotheses": List[hypothesis_dict],
            "tag_profiles": Dict (optional)
        }
        
        Output: {
            "pdf_path": str,
            "html_path": str,
            "json_path": str,
            "summary": {...}
        }
        """
        await self.connect_db()
        
        try:
            anomalies = input_data.get("anomalies", [])
            hypotheses = input_data.get("hypotheses", [])
            tag_profiles = input_data.get("tag_profiles", {})
            
            anomalies = [guardrail.validate_report(a) for a in anomalies]
            hypotheses = [guardrail.validate_hypothesis(h) for h in hypotheses]
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            # Generate PDF (Executive Summary)
            pdf_path = self._generate_pdf(anomalies, hypotheses, timestamp)
            
            # Generate HTML (Detailed Technical Report)
            html_path = self._generate_html(anomalies, hypotheses, tag_profiles, timestamp)
            
            # Generate JSON (Raw Data Export)
            json_path = self._generate_json(anomalies, hypotheses, tag_profiles, timestamp)
            
            result = {
                "pdf_path": str(pdf_path),
                "html_path": str(html_path),
                "json_path": str(json_path),
                "summary": {
                    "anomalies_reported": len(anomalies),
                    "hypotheses_generated": len(hypotheses),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            # LLM executive narrative
            result["ai_executive_summary"] = await self._write_executive_narrative(anomalies, hypotheses)
            
            await self.save_trace(input_data, result)
            return result
            
        finally:
            await self.disconnect_db()
    
    async def _write_executive_narrative(self, anomalies: List, hypotheses: List) -> str:
        """Use LLM to write a compliance-focused executive summary"""
        if not anomalies and not hypotheses:
            return "No anomalies or hypotheses to report. All sensor data within normal parameters."
        
        prompt = PromptTemplate(
            template="""You are a pharma compliance officer writing an executive summary for plant management. In 2-3 sentences, summarize these findings and their compliance implications under FDA 21 CFR Part 11.

Anomalies found: {anomaly_count} across {tag_list}
Root causes identified: {hypothesis_count}
Actions recommended: {action_count}

Focus on: risk level, what needs immediate attention, and compliance status.""",
            input_variables=["anomaly_count", "tag_list", "hypothesis_count", "action_count"]
        )
        
        tag_list = ", ".join(set(a.get("tag_id", "Unknown") for a in anomalies[:6]))
        action_count = sum(1 for h in hypotheses if h.get("recommended_action"))
        
        try:
            chain = prompt | self.llm
            response = await chain.ainvoke({
                "anomaly_count": str(len(anomalies)),
                "tag_list": tag_list,
                "hypothesis_count": str(len(hypotheses)),
                "action_count": str(action_count)
            })
            return response.content if hasattr(response, 'content') else str(response)
        except Exception:
            return f"Report generated with {len(anomalies)} anomalies and {len(hypotheses)} root causes. Review findings for compliance implications."
    
    def _generate_pdf(self, anomalies: List[Dict], hypotheses: List[Dict], timestamp: str) -> Path:
        """Generate executive summary PDF"""
        
        pdf_path = self.reports_dir / f"executive_summary_{timestamp}.pdf"
        doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
        styles = getSampleStyleSheet()
        
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center
        )
        story.append(Paragraph("Pharma Data Integrity Inspector", title_style))
        story.append(Paragraph("Executive Summary Report", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        # Summary statistics
        story.append(Paragraph(f"Report Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Spacer(1, 12))
        
        # Key metrics table
        metrics_data = [
            ['Metric', 'Value'],
            ['Total Anomalies Detected', str(len(anomalies))],
            ['High Severity', str(sum(1 for a in anomalies if a.get('severity') == 'high'))],
            ['Medium Severity', str(sum(1 for a in anomalies if a.get('severity') == 'medium'))],
            ['Low Severity', str(sum(1 for a in anomalies if a.get('severity') == 'low'))],
            ['Hypotheses Generated', str(len(hypotheses))],
        ]
        
        metrics_table = Table(metrics_data, colWidths=[250, 100])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(metrics_table)
        story.append(Spacer(1, 24))
        
        # Top anomalies
        story.append(Paragraph("Top Anomalies Requiring Attention", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        # Sort by severity
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        sorted_anomalies = sorted(anomalies, key=lambda x: severity_order.get(x.get('severity', 'low'), 3))
        
        for i, anomaly in enumerate(sorted_anomalies[:5], 1):
            conf = float(anomaly.get('confidence') or 0)
            story.append(Paragraph(f"<b>{i}. {anomaly['tag_id']}</b> - {anomaly['anomaly_type'].replace('_', ' ').title()}", styles['Heading3']))
            story.append(Paragraph(f"Severity: {str(anomaly.get('severity', 'unknown')).upper()} | Confidence: {conf*100:.0f}%", styles['Normal']))
            
            # Find corresponding hypothesis
            hypothesis = next((h for h in hypotheses if h.get('anomaly_id') == anomaly.get('id')), None)
            if hypothesis:
                story.append(Paragraph(f"<i>Root Cause:</i> {hypothesis['root_cause']}", styles['Normal']))
                story.append(Paragraph(f"<i>Recommended Action:</i> {hypothesis['recommended_action']}", styles['Normal']))
            
            story.append(Spacer(1, 12))
        
        # Pharma compliance note
        story.append(Paragraph("Compliance Notes", styles['Heading2']))
        story.append(Spacer(1, 12))
        
        fda_anomalies = [a for a in anomalies if 'fda' in a.get('anomaly_type', '').lower()]
        if fda_anomalies:
            story.append(Paragraph("<b>FDA 21 CFR Part 11 Concerns:</b>", styles['Normal']))
            for anomaly in fda_anomalies:
                story.append(Paragraph(f"- {anomaly['tag_id']}: {anomaly.get('pharma_impact', 'Review required')}", styles['Normal']))
        else:
            story.append(Paragraph("No critical FDA compliance issues detected in this reporting period.", styles['Normal']))
        
        story.append(Spacer(1, 24))
        story.append(Paragraph("--- End of Executive Summary ---", styles['Normal']))
        
        doc.build(story)
        return pdf_path
    
    def _generate_html(self, anomalies: List[Dict], hypotheses: List[Dict], tag_profiles: Dict, timestamp: str) -> Path:
        """Generate detailed HTML report"""
        
        html_path = self.reports_dir / f"detailed_report_{timestamp}.html"
        
        template = Template("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pharma Data Integrity - Detailed Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-gray-50">
    <div class="max-w-7xl mx-auto p-8">
        <!-- Header -->
        <header class="mb-8">
            <h1 class="text-3xl font-bold text-gray-900">Pharma Data Integrity Inspector</h1>
            <p class="text-gray-600 mt-2">Detailed Technical Report</p>
            <p class="text-sm text-gray-500 mt-1">Generated: {{ generated_at }}</p>
        </header>
        
        <!-- Summary Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-gray-600">Total Anomalies</p>
                <p class="text-3xl font-bold text-gray-900 mt-2">{{ total_anomalies }}</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-gray-600">High Severity</p>
                <p class="text-3xl font-bold text-red-600 mt-2">{{ high_severity }}</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-gray-600">Hypotheses Generated</p>
                <p class="text-3xl font-bold text-blue-600 mt-2">{{ total_hypotheses }}</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-gray-600">Tags Analyzed</p>
                <p class="text-3xl font-bold text-green-600 mt-2">{{ tags_analyzed }}</p>
            </div>
        </div>
        
        <!-- Anomalies Table -->
        <div class="bg-white rounded-lg shadow mb-8">
            <div class="px-6 py-4 border-b border-gray-200">
                <h2 class="text-xl font-semibold text-gray-900">Detected Anomalies</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tag ID</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Anomaly Type</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Severity</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Confidence</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Evidence</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        {% for anomaly in anomalies %}
                        <tr class="hover:bg-gray-50">
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ anomaly.tag_id }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ anomaly.anomaly_type | replace('_', ' ') | title }}</td>
                            <td class="px-6 py-4 whitespace-nowrap">
                                <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                                    {% if anomaly.severity == 'critical' %}bg-purple-100 text-purple-800
                                    {% elif anomaly.severity == 'high' %}bg-red-100 text-red-800
                                    {% elif anomaly.severity == 'medium' %}bg-yellow-100 text-yellow-800
                                    else %}bg-green-100 text-green-800{% endif %}">
                                    {{ anomaly.severity | upper }}
                                </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ (anomaly.confidence * 100) | round(0) }}%</td>
                            <td class="px-6 py-4 text-sm text-gray-600 max-w-md truncate">{{ anomaly.evidence }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Hypotheses Section -->
        <div class="bg-white rounded-lg shadow mb-8">
            <div class="px-6 py-4 border-b border-gray-200">
                <h2 class="text-xl font-semibold text-gray-900">Root Cause Hypotheses</h2>
            </div>
            <div class="p-6 space-y-6">
                {% for hypothesis in hypotheses %}
                <div class="border-l-4 border-blue-500 pl-4">
                    <div class="flex items-center justify-between mb-2">
                        <h3 class="text-lg font-medium text-gray-900">{{ hypothesis.tag_id }}</h3>
                        <span class="text-sm text-gray-500">Confidence: {{ (hypothesis.confidence * 100) | round(0) }}%</span>
                    </div>
                    <p class="text-gray-700 mb-2"><strong>Root Cause:</strong> {{ hypothesis.root_cause }}</p>
                    <p class="text-gray-700 mb-2"><strong>Recommended Action:</strong> {{ hypothesis.recommended_action }}</p>
                    {% if hypothesis.alternative_causes %}
                    <p class="text-sm text-gray-600"><strong>Alternative Causes:</strong> {{ hypothesis.alternative_causes | join(', ') }}</p>
                    {% endif %}
                    {% if hypothesis.pharma_impact %}
                    <p class="text-sm text-red-600 mt-2"><strong>Pharma Impact:</strong> {{ hypothesis.pharma_impact }}</p>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
        
        <!-- Tag Statistics -->
        <div class="bg-white rounded-lg shadow">
            <div class="px-6 py-4 border-b border-gray-200">
                <h2 class="text-xl font-semibold text-gray-900">Tag Statistics Summary</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tag ID</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Mean</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Std Dev</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Min</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Max</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data Completeness</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        {% for tag_id, profile in tag_profiles.items() %}
                        <tr class="hover:bg-gray-50">
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ tag_id }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ profile.mean | round(2) }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ profile.std | round(2) }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ profile.min | round(2) }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ profile.max | round(2) }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{{ profile.data_completeness }}%</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Footer -->
        <footer class="mt-8 text-center text-sm text-gray-500">
            <p>Pharma Data Integrity Inspector v1.0.0</p>
            <p>Built with LangChain Multi-Agent System</p>
        </footer>
    </div>
</body>
</html>
        """)
        
        html_content = template.render(
            generated_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            total_anomalies=len(anomalies),
            high_severity=sum(1 for a in anomalies if a.get('severity') == 'high'),
            total_hypotheses=len(hypotheses),
            tags_analyzed=len(tag_profiles),
            anomalies=anomalies,
            hypotheses=hypotheses,
            tag_profiles=tag_profiles
        )
        
        html_path.write_text(html_content)
        return html_path
    
    def _generate_json(self, anomalies: List[Dict], hypotheses: List[Dict], tag_profiles: Dict, timestamp: str) -> Path:
        """Generate raw JSON data export"""
        
        json_path = self.reports_dir / f"raw_data_{timestamp}.json"
        
        export_data = {
            "metadata": {
                "report_type": "raw_data_export",
                "generated_at": datetime.utcnow().isoformat(),
                "system": "Pharma Data Integrity Inspector",
                "version": "1.0.0"
            },
            "anomalies": anomalies,
            "hypotheses": hypotheses,
            "tag_profiles": tag_profiles,
            "summary": {
                "total_anomalies": len(anomalies),
                "total_hypotheses": len(hypotheses),
                "tags_analyzed": len(tag_profiles),
                "by_severity": {
                    "critical": sum(1 for a in anomalies if a.get('severity') == 'critical'),
                    "high": sum(1 for a in anomalies if a.get('severity') == 'high'),
                    "medium": sum(1 for a in anomalies if a.get('severity') == 'medium'),
                    "low": sum(1 for a in anomalies if a.get('severity') == 'low'),
                },
                "by_type": self._count_by_type(anomalies)
            }
        }
        
        json_path.write_text(json.dumps(export_data, indent=2, default=str))
        return json_path
    
    def _count_by_type(self, anomalies: List[Dict]) -> Dict[str, int]:
        """Count anomalies by type"""
        counts = {}
        for a in anomalies:
            atype = a.get('anomaly_type', 'unknown')
            counts[atype] = counts.get(atype, 0) + 1
        return counts

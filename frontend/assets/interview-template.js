/* ============================================================
   MeetMind — Interview Evaluation template (loaded by index.html)
   ------------------------------------------------------------
   Adds the Interview Evaluation template: an interview-details /
   required-skills card and a report card, shown only while the
   "interview" template is selected (see interview-template.css).
   The recorder, upload and transcript are shared with the other
   templates; this evaluates the transcript on screen through
   POST /api/interview/analyze (backend/interview_routes.py) and
   renders the result as a report that can be downloaded as an
   editable HTML file or printed / saved as PDF.

   Template switching itself lives in doctor-template.js, which
   dispatches "meetmind:template-changed". Nothing here is saved
   to meeting or consultation history.
============================================================ */

(function () {
  "use strict";

  // ---- mount the two cards after the transcript panel ----
  var CARDS_HTML =
    '<section id="interviewSetupCard" class="card iv-card" hidden>' +
      '<div class="panel-head"><h2>Interview Details &amp; Required Skills</h2></div>' +
      '<p class="iv-note">Enter the interview details and skills to assess. Record or upload the interview using the existing controls; after transcription, run the evaluation.</p>' +
      '<div class="iv-grid">' +
        '<label>Candidate name<input id="interviewCandidateName" autocomplete="off" placeholder="Candidate name"></label>' +
        '<label>Interviewer name<input id="interviewInterviewerName" autocomplete="off" placeholder="Interviewer name"></label>' +
        '<label>Position / role<input id="interviewPosition" autocomplete="off" placeholder="e.g. Python Developer"></label>' +
        '<label>Interview type<select id="interviewType"><option>Technical</option><option>HR</option><option>Behavioral</option><option>Mixed</option></select></label>' +
        '<label class="iv-span">Required skills (comma-separated)<textarea id="interviewRequiredSkills" rows="3" placeholder="e.g. Python, SQL, REST APIs, problem solving"></textarea></label>' +
      '</div>' +
      '<div class="iv-actions">' +
        '<button type="button" id="analyzeInterviewBtn" class="iv-btn iv-btn-primary">Evaluate Interview</button>' +
        '<span id="interviewAnalysisStatus" class="iv-status" role="status"></span>' +
      '</div>' +
    '</section>' +
    '<section id="interviewReportCard" class="card iv-card" hidden>' +
      '<div class="panel-head"><h2>Interview Evaluation Report</h2></div>' +
      '<div class="iv-actions">' +
        '<button type="button" id="downloadInterviewReportBtn" class="iv-btn iv-btn-primary">Download Report (Editable HTML)</button>' +
        '<button type="button" id="printInterviewReportBtn" class="iv-btn">Print / Save PDF</button>' +
      '</div>' +
      '<div id="interviewReportContent" class="intelligence" aria-live="polite"></div>' +
    '</section>';

  var transcriptPanel = document.querySelector(".panel--transcript");
  if (!transcriptPanel || !transcriptPanel.parentNode) return;
  var mount = document.createElement("div");
  mount.innerHTML = CARDS_HTML;
  var anchor = transcriptPanel.nextSibling;
  while (mount.firstChild) transcriptPanel.parentNode.insertBefore(mount.firstChild, anchor);

  // ---- show / clear with the selected template ----
  function syncVisibility() {
    var active = document.body.dataset.meetmindTemplate === "interview";
    document.getElementById("interviewSetupCard").hidden = !active;
    if (!active) document.getElementById("interviewReportCard").hidden = true;
  }
  document.addEventListener("meetmind:template-changed", syncVisibility);

  // A new recording or upload starts a new interview: drop the old report.
  document.addEventListener("meetmind:new-session", function () {
    document.getElementById("interviewReportCard").hidden = true;
    document.getElementById("interviewReportContent").innerHTML = "";
    document.getElementById("interviewAnalysisStatus").textContent = "";
  });

  syncVisibility();

  const btn=document.getElementById("analyzeInterviewBtn");
  const status=document.getElementById("interviewAnalysisStatus");
  const card=document.getElementById("interviewReportCard");
  const output=document.getElementById("interviewReportContent");
  if(!btn||!status||!card||!output)return;
  const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const get=(o,...keys)=>{for(const k of keys)if(o&&o[k]!=null)return o[k];return "";};
  const section=(title,body)=>'<section class="interview-report-section"><h3>'+esc(title)+'</h3>'+body+'</section>';
  const list=items=>Array.isArray(items)&&items.length?'<ul>'+items.map(x=>'<li>'+esc(typeof x==="string"?x:(x.text||x.description||JSON.stringify(x)))+'</li>').join("")+'</ul>':"<p>Not provided.</p>";
  btn.addEventListener("click",async()=>{
    const textValue=(typeof transcript!=="undefined"?transcript:"").trim();
    const skills=document.getElementById("interviewRequiredSkills").value.split(",").map(x=>x.trim()).filter(Boolean);
    if(!textValue){status.textContent="Record or upload an interview first so a transcript is available.";return;}
    if(!skills.length){status.textContent="Enter at least one required skill.";return;}
    btn.disabled=true;status.textContent="Evaluating interview with Qwen3-27B...";card.hidden=true;
    try{
      const response=await fetch("/api/interview/analyze",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({
        transcript:textValue,required_skills:skills,
        candidate_name:document.getElementById("interviewCandidateName").value.trim(),
        interviewer_name:document.getElementById("interviewInterviewerName").value.trim(),
        position:document.getElementById("interviewPosition").value.trim(),
        interview_type:document.getElementById("interviewType").value
      })});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.detail||data.error||"Interview evaluation failed.");
      const qa=get(data,"qa_analysis","questions_and_answers")||[];
      const assessments=get(data,"skill_assessment","skills_assessment")||[];
      const details=[["Candidate",document.getElementById("interviewCandidateName").value],["Interviewer",document.getElementById("interviewInterviewerName").value],["Position",document.getElementById("interviewPosition").value],["Interview type",document.getElementById("interviewType").value]].filter(x=>x[1]).map(x=>'<p><strong>'+esc(x[0])+':</strong> '+esc(x[1])+'</p>').join("")||"<p>Details not entered.</p>";
      const qaRows=Array.isArray(qa)?qa.map((x,i)=>'<tr><td>'+(i+1)+'</td><td>'+esc(get(x,"question","interviewer_question"))+'</td><td>'+esc(get(x,"candidate_answer","answer","participant_answer"))+'</td><td>'+esc(get(x,"related_skill","skill"))+'</td><td>'+esc(get(x,"evaluation","answer_evaluation","correctness"))+'</td><td>'+esc(get(x,"expected_answer","correct_answer","ideal_answer"))+'</td></tr>').join(""):"";
      const skillRows=Array.isArray(assessments)?assessments.map(x=>'<tr><td>'+esc(get(x,"skill","name"))+'</td><td>'+esc(get(x,"proficiency_level","level"))+'</td><td>'+esc(get(x,"score","percentage"))+'</td><td>'+esc(get(x,"evidence","justification","summary"))+'</td></tr>').join(""):"";
      const evalLabels=Array.isArray(qa)?qa.map(x=>String(get(x,"evaluation","answer_evaluation","correctness")).trim().toLowerCase()):[];
      const correctCount=evalLabels.filter(v=>v==="correct"||v==="fully correct").length;
      const partialCount=evalLabels.filter(v=>v.includes("partial")).length;
      const incorrectCount=evalLabels.filter(v=>v==="incorrect"||v==="wrong").length;
      const unableCount=evalLabels.filter(v=>v.includes("unable")||v.includes("insufficient")||v.includes("not evaluated")).length;
      const evaluatedCount=correctCount+partialCount+incorrectCount;
      const overallScore=evaluatedCount?Math.round(((correctCount+partialCount*0.5)/evaluatedCount)*100)+"%":"Not available";
      const performanceRows='<div class="interview-performance-grid">'+
        '<div class="interview-performance-metric"><strong>'+qa.length+'</strong><span>Total Questions</span></div>'+
        '<div class="interview-performance-metric"><strong>'+correctCount+'</strong><span>Correct</span></div>'+
        '<div class="interview-performance-metric"><strong>'+partialCount+'</strong><span>Partially Correct</span></div>'+
        '<div class="interview-performance-metric"><strong>'+incorrectCount+'</strong><span>Incorrect</span></div>'+
        '<div class="interview-performance-metric"><strong>'+unableCount+'</strong><span>Unable to Evaluate</span></div>'+
        '<div class="interview-performance-metric"><strong>'+overallScore+'</strong><span>Overall Score*</span></div></div>'+
        '<p class="interview-performance-note">*Score is calculated as (Correct + 0.5 × Partially Correct) ÷ evaluable answers. Unable-to-evaluate answers are excluded.</p>';
      output.innerHTML=section("Interview Details",details)+section("Required Skills",'<div>'+skills.map(x=>'<span class="interview-skill">'+esc(x)+'</span>').join("")+'</div>')+
        section("Overall Performance",performanceRows)+
        section("Question & Answer Analysis",qaRows?'<div style="overflow-x:auto"><table class="interview-report-table"><thead><tr><th>#</th><th>Question</th><th>Candidate answer</th><th>Related skill</th><th>Evaluation</th><th>Expected answer</th></tr></thead><tbody>'+qaRows+'</tbody></table></div>':"<p>No question-and-answer analysis was returned.</p>")+
        section("Skill-wise Assessment",skillRows?'<div style="overflow-x:auto"><table class="interview-report-table"><thead><tr><th>Skill</th><th>Proficiency</th><th>Score</th><th>Evidence</th></tr></thead><tbody>'+skillRows+'</tbody></table></div>':"<p>No skill assessment was returned.</p>")+
        section("Strengths",list(get(data,"strengths","strengths_identified")))+section("Areas for Improvement",list(get(data,"improvement_areas","areas_for_improvement")))+section("Conclusion","<p>"+esc(get(data,"conclusion","overall_conclusion","overall_assessment")||"Not provided.")+"</p>");
      card.hidden=false;status.textContent="Interview evaluation completed.";card.scrollIntoView({behavior:"smooth",block:"start"});
    }catch(error){status.textContent=error.message||"Interview evaluation failed.";}
    finally{btn.disabled=false;}
  });

  // Download a standalone, editable HTML copy of the generated interview report.
  const downloadBtn=document.getElementById("downloadInterviewReportBtn");
  const printBtn=document.getElementById("printInterviewReportBtn");
  if(downloadBtn){
    downloadBtn.addEventListener("click",()=>{
      if(card.hidden || !output.innerHTML.trim()) { status.textContent="Generate the interview evaluation report first."; return; }
      const candidate=(document.getElementById("interviewCandidateName")?.value||"Candidate").trim();
      const safeCandidate=candidate.replace(/[^a-z0-9_-]+/gi,"_")||"Candidate";
      const details={candidate,interviewer:document.getElementById("interviewInterviewerName")?.value||"",position:document.getElementById("interviewPosition")?.value||"",type:document.getElementById("interviewType")?.value||"Technical",skills:document.getElementById("interviewRequiredSkills")?.value||""};
      const escHtml=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
      const reportHtml=output.innerHTML;
      const standalone=`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MeetMind Interview Evaluation - ${escHtml(candidate)}</title><style>
:root{--navy:#102a72;--blue:#1769e8;--pale:#edf5ff;--line:#d8e4f4;--ink:#1d2b45;--muted:#61718b}*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:var(--ink);font:14px/1.5 Arial,sans-serif}.toolbar{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:12px;display:flex;gap:8px;justify-content:flex-end}.toolbar button{border:0;border-radius:7px;padding:10px 14px;font-weight:bold;cursor:pointer;background:var(--blue);color:white}.page{max-width:1100px;margin:22px auto;background:#fff;padding:26px;border:1px solid var(--line);border-radius:12px}header{display:flex;justify-content:space-between;gap:16px;align-items:center;border-bottom:2px solid var(--blue);padding-bottom:14px;margin-bottom:18px}.brand{font-size:24px;font-weight:800;color:var(--navy)}.muted{font-size:12px;color:var(--muted)}.details{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px;background:var(--pale);padding:14px;border-radius:8px;margin-bottom:18px}.interview-performance-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.interview-performance-metric{padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--pale);text-align:center}.interview-performance-metric strong{display:block;font-size:21px;color:var(--navy);margin-bottom:3px}.interview-performance-metric span{font-size:12px;color:var(--muted)}.interview-performance-note{font-size:11px;color:var(--muted);margin-top:10px}.interview-report-section{margin:18px 0;padding:14px;border:1px solid var(--line);border-radius:9px;break-inside:avoid}.interview-report-section h3{color:var(--navy);margin:0 0 10px;font-size:16px}.interview-report-table{width:100%;border-collapse:collapse;font-size:12px}.interview-report-table th{background:#e9f1fb;color:var(--navy);text-align:left}.interview-report-table th,.interview-report-table td{border:1px solid var(--line);padding:8px;vertical-align:top}.interview-skill{display:inline-block;margin:3px;padding:5px 9px;border:1px solid var(--line);border-radius:99px;background:var(--pale)}[contenteditable=true]{outline:1px dashed #b8c7df;outline-offset:2px}@media(max-width:700px){.page{margin:0;padding:12px}.details{grid-template-columns:1fr}table{display:block;overflow-x:auto}}@media print{body{background:white}.toolbar{display:none}.page{margin:0;max-width:none;border:0;padding:0}.interview-report-section{break-inside:avoid}}
</style></head><body><div class="toolbar"><button onclick="document.querySelectorAll('[contenteditable]').forEach(e=>e.contentEditable='true');alert('Edit mode enabled. Click any report text to edit it.')">Edit Report</button><button onclick="window.print()">Print / Save PDF</button></div><main class="page"><header><div><div class="brand">◉ MeetMind</div><div class="muted">AI-assisted interview evaluation</div></div><div><strong>Interview Evaluation Report</strong><div class="muted">Generated ${new Date().toLocaleDateString()}</div></div></header><section class="details"><div><b>Candidate:</b> ${escHtml(details.candidate)||'Not provided'}</div><div><b>Interviewer:</b> ${escHtml(details.interviewer)||'Not provided'}</div><div><b>Position / Role:</b> ${escHtml(details.position)||'Not provided'}</div><div><b>Interview Type:</b> ${escHtml(details.type)}</div><div style="grid-column:1/-1"><b>Required Skills:</b> ${escHtml(details.skills)||'Not provided'}</div></section><div id="report" contenteditable="true">${reportHtml}</div><p class="muted">AI-assisted evaluation. Verify uncertain transcripts and assessments before using this report for hiring decisions.</p></main></body></html>`;
      const blob=new Blob([standalone],{type:"text/html;charset=utf-8"});
      const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=`MeetMind_Interview_Evaluation_${safeCandidate}.html`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
      status.textContent="Editable interview report downloaded.";
    });
  }
  if(printBtn){
    printBtn.addEventListener("click",()=>{
      if(card.hidden || !output.innerHTML.trim()){
        status.textContent="Generate the interview evaluation report first.";
        return;
      }
      const candidate=(document.getElementById("interviewCandidateName")?.value||"Candidate").trim();
      const reportWindow=window.open("","_blank");
      if(!reportWindow){
        status.textContent="Please allow pop-ups to print the report.";
        return;
      }
      const reportHtml=output.innerHTML;
      reportWindow.document.open();
      reportWindow.document.write(`<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MeetMind_Interview_Evaluation_${candidate.replace(/[^a-z0-9_-]+/gi,"_")}</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:28px;color:#1d2b45;background:#fff;font:13px/1.55 Arial,sans-serif}
header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #4f46e5;padding-bottom:14px;margin-bottom:20px}
.brand{font-size:22px;font-weight:800;color:#102a72}
.muted{font-size:11px;color:#61718b}
h1{font-size:20px;margin:0;color:#102a72}
h2,h3{color:#102a72;margin:18px 0 8px}
section{margin:0 0 18px;break-inside:avoid}
table{width:100%;border-collapse:collapse;font-size:10px;table-layout:fixed}
th{background:#edf5ff;color:#102a72;text-align:left}
th,td{border:1px solid #d8e4f4;padding:7px;vertical-align:top;overflow-wrap:anywhere;word-break:normal}
ul{padding-left:22px}
.interview-performance-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.interview-performance-metric{border:1px solid #d8e4f4;padding:9px;text-align:center}.interview-performance-metric strong{display:block;font-size:18px;color:#102a72}.interview-performance-metric span{font-size:10px}.interview-performance-note{font-size:9px;color:#61718b}
main table:has(th:nth-child(6)) th:nth-child(1),main table:has(th:nth-child(6)) td:nth-child(1){width:4%}
main table:has(th:nth-child(6)) th:nth-child(2),main table:has(th:nth-child(6)) td:nth-child(2){width:17%}
main table:has(th:nth-child(6)) th:nth-child(3),main table:has(th:nth-child(6)) td:nth-child(3){width:25%}
main table:has(th:nth-child(6)) th:nth-child(4),main table:has(th:nth-child(6)) td:nth-child(4){width:12%;min-width:90px}
main table:has(th:nth-child(6)) th:nth-child(5),main table:has(th:nth-child(6)) td:nth-child(5){width:12%}
main table:has(th:nth-child(6)) th:nth-child(6),main table:has(th:nth-child(6)) td:nth-child(6){width:30%}
main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) th:nth-child(1),main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) td:nth-child(1){width:17%;min-width:100px}
main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) th:nth-child(2),main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) td:nth-child(2){width:20%}
main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) th:nth-child(3),main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) td:nth-child(3){width:10%}
main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) th:nth-child(4),main table:has(th:nth-child(4)):not(:has(th:nth-child(6))) td:nth-child(4){width:53%}
.interview-skill{display:inline-block;margin:3px 7px 3px 0;padding:5px 9px;white-space:nowrap}
@page{size:landscape;margin:10mm}
@media print{body{padding:0}section,table,tr{break-inside:avoid-page}thead{display:table-header-group}}
</style></head><body>
<header><div><div class="brand">MeetMind</div><div class="muted">AI-assisted interview evaluation</div></div><div><h1>Interview Evaluation Report</h1><div class="muted">Candidate: ${candidate.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}</div><div class="muted">Generated ${new Date().toLocaleDateString()}</div></div></header>
<main>${reportHtml}</main>
<script>window.addEventListener("load",()=>{setTimeout(()=>window.print(),300)});<\/script>
</body></html>`);
      reportWindow.document.close();
      status.textContent="Opened a report-only print view. Choose Save as PDF in the print dialog.";
    });
  }
})();

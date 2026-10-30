/* Support tab: check all upcoming unfinished study sessions, across every course.
   Show exactly one collision proposal at a time. One visible confirmation
   triggers server-side preview and explicit confirm; no generative AI edits. */
window.FloatingAiSchedule = (function () {
  "use strict";

  // Retained for other consumers, but academic questions are never intercepted.
  function isRequest(text) {
    const q = String(text || "").toLocaleLowerCase("vi-VN");
    return /trùng lịch|trùng giờ|đụng lịch|đụng giờ|lịch bị trùng|lịch trùng|kiểm tra lịch|xem lịch học|lịch học của (tôi|mình|tui|em)|đổi lịch|dời lịch|sửa lịch|chỉnh lịch|chuyển lịch|đổi giờ học|chỉnh giờ học|dời giờ học|dời buổi học|đổi buổi học|giờ trống|thời khóa biểu|sắp xếp lịch/.test(q);
  }

  function attach({results, actionButton, setStatus}) {
    if (!results || !actionButton) {
      return {open:async()=>{},reset:()=>{},isRequest};
    }
    let pending = false;
    let generation = 0;
    const el = (tag, klass, value) => {
      const node = document.createElement(tag);
      if (klass) node.className = klass;
      if (value != null) node.textContent = String(value);
      return node;
    };
    const date = iso => (typeof iso === "string" && iso.length >= 16)
      ? iso.slice(8,10)+"/"+iso.slice(5,7)+"/"+iso.slice(0,4)+" · "+iso.slice(11,16)
      : "Chưa xác định";
    async function api(url, options = {}) {
      const response = await fetch(url, {credentials:"same-origin",...options});
      const value = await response.json().catch(() => ({}));
      if (!response.ok) throw Error(value.error || "Chưa kiểm tra được lịch học.");
      return value;
    }
    function post(url, csrf, body) {
      return api(url, {
        method:"POST",
        headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},
        body:JSON.stringify(body)
      });
    }
    function clear() {results.replaceChildren();}
    function message(text, icon="calendar-check") {
      const note = el("p","floating-ai-review-empty",text);
      note.dataset.status=icon;
      results.appendChild(note);
    }
    function reset() {
      generation++;
      clear();
      message("Chọn “Rà soát toàn bộ lịch học” để kiểm tra các buổi chưa hoàn thành.");
    }
    async function open(success) {
      if (pending) return;
      pending=true;
      const token=++generation;
      actionButton.disabled=true;
      clear();
      message("Đang rà soát toàn bộ lịch học...");
      try {
        const data=await api("/api/chat/schedule/review");
        if (token!==generation) return;
        clear();
        const count=Number(data.conflict_count||0);
        const heading=el("div","floating-ai-review-summary");
        heading.appendChild(el("strong",null,count
          ? "⚠ Có "+count+" buổi cần rà soát"
          : "✓ Không có buổi học trùng giờ"));
        heading.appendChild(el("span",null,
          "Đã kiểm tra "+Number(data.checked_count||0)+" buổi học sắp tới"));
        results.appendChild(heading);
        if (success) {
          const done=el("p","floating-ai-review-success",success);
          results.appendChild(done);
        }
        const task=data.next_conflict;
        if (!count) {
          message("Các buổi chưa hoàn thành trong lịch tương lai không bị trùng giờ.");
          setStatus("Đã rà soát lịch học");
          return;
        }
        if (!task) {
          message("Chưa thể đề xuất giờ an toàn cho những buổi trùng. Hãy kiểm tra dữ liệu môn học và thử lại.");
          return;
        }
        const card=el("article","floating-ai-review-card");
        card.appendChild(el("div","floating-ai-review-subject",
                            task.subject_name+" · "+task.title));
        const overlaps=Array.isArray(task.conflict_titles)?task.conflict_titles:[];
        if (overlaps.length) card.appendChild(el("p","floating-ai-review-warning",
          "Trùng với: "+overlaps.join(", ")));
        const times=el("div","floating-ai-review-times");
        const oldTime=el("div","floating-ai-review-time");
        oldTime.appendChild(el("small",null,"LỊCH HIỆN TẠI"));
        oldTime.appendChild(el("strong",null,date(task.study_at)));
        times.appendChild(oldTime);
        times.appendChild(el("span","floating-ai-review-arrow","→"));
        const newTime=el("div","floating-ai-review-time");
        newTime.appendChild(el("small",null,"GIỜ TRỐNG ĐỀ XUẤT"));
        newTime.appendChild(el("strong",null,
          task.suggested_at?date(task.suggested_at):"Chưa có"));
        times.appendChild(newTime);card.appendChild(times);

        if (task.suggested_at) {
          const confirm=el("button","floating-ai-schedule-confirm","✓ Xác nhận đổi giờ");
          confirm.type="button";
          const feedback=el("p","floating-ai-schedule-result","");
          feedback.setAttribute("role","status");
          confirm.addEventListener("click",async()=>{
            if (pending) return;
            pending=true;
            confirm.disabled=true;actionButton.disabled=true;
            feedback.textContent="Đang kiểm tra và cập nhật giờ học...";
            try {
              // Both requests are initiated by a user's single explicit click.
              // The second call never runs if a stale schedule fails preview.
              const preview=await post("/api/chat/schedule/preview",data.csrf_token,{
                conversation_id:task.conversation_id,
                task_id:task.id,study_at:task.suggested_at
              });
              if (token!==generation) return;
              const saved=await post("/api/chat/schedule/confirm",data.csrf_token,{
                conversation_id:task.conversation_id,
                proposal_id:preview.proposal_id
              });
              if (token!==generation) return;
              feedback.textContent="✓ Đã cập nhật lịch học.";
              pending=false;
              await open("Đã đổi “"+saved.title+"” sang "+date(saved.study_at)+".");
            } catch(error) {
              if (token===generation) {
                feedback.textContent=error.message+
                  " Lịch chưa thay đổi, hãy rà soát lại.";
                setStatus("Chưa đổi lịch");
              }
            } finally {
              pending=false;
              confirm.disabled=false;actionButton.disabled=false;
            }
          });
          card.appendChild(confirm);
          card.appendChild(feedback);
        } else {
          card.appendChild(el("p","floating-ai-review-warning",
            "Chưa có giờ trống phù hợp để tự đề xuất cho buổi này."));
        }
        results.appendChild(card);
        setStatus("Đã rà soát lịch học");
      } catch(error) {
        if (token!==generation) return;
        clear();message(error.message);
        setStatus("Rà soát chưa thành công");
      } finally {
        pending=false;
        actionButton.disabled=false;
      }
    }
    actionButton.addEventListener("click",()=>{open();});
    return {open,reset,isRequest};
  }
  return {attach,isRequest};
})();

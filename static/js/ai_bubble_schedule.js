/* Schedule actions inside the floating chat: deterministic, no model-generated writes.
   Every change is previewed and explicitly confirmed against the live database. */
window.FloatingAiSchedule = (function () {
  "use strict";
  function isRequest(text) {
    const q = String(text || "").toLocaleLowerCase("vi-VN");
    return /trùng lịch|trùng giờ|đụng lịch|đụng giờ|lịch bị trùng|kiểm tra lịch|xem lịch học|lịch học của (tôi|mình|tui|em)|đổi lịch|dời lịch|chuyển lịch|đổi giờ học|dời giờ học|giờ trống|thời khóa biểu|sắp xếp lịch/.test(q);
  }

  function attach(options) {
    const {messages, actionButton, getConversationId, getSubjectId,
           appendMessage, setStatus} = options;
    let active = null;
    let pending = false;

    const el = (name, className, label) => {
      const node = document.createElement(name);
      if (className) node.className = className;
      if (label) node.textContent = label;
      return node;
    };
    function textDate(iso) {
      if (typeof iso !== "string" || iso.length < 16) return "Chưa có giờ";
      return iso.slice(8,10) + "/" + iso.slice(5,7) + "/" +
        iso.slice(0,4) + " · " + iso.slice(11,16);
    }
    async function json(url, opts = {}) {
      const response = await fetch(url, {credentials:"same-origin", ...opts});
      const value = await response.json().catch(() => ({}));
      if (!response.ok) {
        const problem = new Error(value.error || "Không thể xử lý lịch học.");
        problem.suggested_at = value.suggested_at || "";
        throw problem;
      }
      return value;
    }
    function post(path, csrf, body) {
      return json(path, {
        method:"POST",
        headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},
        body:JSON.stringify(body)
      });
    }
    async function conversationForSubject() {
      const current = getConversationId();
      if (Number.isSafeInteger(current) && current > 0) return current;
      const subject = getSubjectId();
      if (!Number.isSafeInteger(subject) || subject <= 0) throw new Error("Hãy chọn môn học trước.");
      const chats = await json("/api/chats");
      const chosen = Array.isArray(chats) ? chats.find(
        x => Number(x.subject_id) === subject && Number(x.id) > 0) : null;
      if (!chosen) throw new Error("Không tìm thấy cuộc trò chuyện của môn học này.");
      return Number(chosen.id);
    }
    function reset() {
      active?.remove();
      active=null;
    }
    async function open() {
      if (pending) return;
      pending=true;
      if (actionButton) actionButton.disabled=true;
      const oldSubject=getSubjectId();
      setStatus("Đang kiểm tra lịch học...");
      try {
        const conversation = await conversationForSubject();
        const data = await json("/api/chat/schedule?conversation_id=" +
          encodeURIComponent(conversation));
        if (getSubjectId() !== oldSubject) return;
        reset();

        const card=el("section","floating-ai-schedule-card");
        card.setAttribute("aria-label","Kiểm tra và đổi lịch học");
        active=card;
        const head=el("div","floating-ai-schedule-head");
        const heading=el("strong",null,"🗓 Lịch học · "+data.subject_name);
        const dismiss=el("button","floating-ai-schedule-close","×");
        dismiss.type="button";dismiss.setAttribute("aria-label","Đóng đề xuất lịch");
        dismiss.addEventListener("click",reset);
        head.append(heading,dismiss);card.appendChild(head);
        const conflicts=Number(data.conflict_count || 0);
        card.appendChild(el("p","floating-ai-schedule-summary",conflicts
          ? "⚠ Có "+conflicts+" buổi trùng giờ. Chọn buổi để xem và đổi sang giờ trống."
          : "Không có buổi trùng giờ trong môn này. Bạn vẫn có thể chọn một buổi để đổi giờ."));
        if (data.limited) card.appendChild(el("p","floating-ai-schedule-hint",
          "Danh sách chỉ hiển thị một phần lịch. Các giờ bận khác vẫn được kiểm tra."));
        const tasks=Array.isArray(data.tasks)?data.tasks:[];
        if (!tasks.length) {
          card.appendChild(el("p","floating-ai-schedule-hint",
            "Môn này chưa có buổi học chưa hoàn thành để đổi lịch."));
          messages.appendChild(card);messages.scrollTop=messages.scrollHeight;
          setStatus("Đã kiểm tra lịch");return;
        }
        const label=el("label","floating-ai-schedule-label","Chọn buổi học");
        const selector=el("select","floating-ai-schedule-select");
        selector.setAttribute("aria-label","Chọn buổi cần đổi giờ");
        for (const task of tasks) {
          const option=el("option",null,
            (task.conflict_titles?.length ? "⚠ " : "") +
            task.title+" · "+textDate(task.study_at));
          option.value=String(task.id);
          selector.appendChild(option);
        }
        label.appendChild(selector);card.appendChild(label);
        const note=el("p","floating-ai-schedule-hint");
        card.appendChild(note);
        const timeLabel=el("label","floating-ai-schedule-label","Chọn ngày và giờ mới");
        const time=el("input","floating-ai-schedule-time");
        time.type="datetime-local";time.required=true;
        timeLabel.appendChild(time);card.appendChild(timeLabel);
        const suggestion=el("button","floating-ai-schedule-suggestion");
        suggestion.type="button";suggestion.hidden=true;
        card.appendChild(suggestion);
        const preview=el("button","floating-ai-schedule-preview","Kiểm tra giờ mới");
        preview.type="button";card.appendChild(preview);
        const result=el("p","floating-ai-schedule-result");
        result.setAttribute("role","status");card.appendChild(result);
        const confirm=el("button","floating-ai-schedule-confirm","✓ Xác nhận đổi lịch");
        confirm.type="button";confirm.hidden=true;card.appendChild(confirm);
        let proposal=null;
        const selectedTask=()=>tasks.find(x=>String(x.id)===selector.value);
        function resetProposal() {
          proposal=null;confirm.hidden=true;result.textContent="";
        }
        function chooseTask() {
          resetProposal();
          const task=selectedTask();
          if (!task) return;
          time.value=task.suggested_at || task.study_at;
          const overlaps=Array.isArray(task.conflict_titles)?task.conflict_titles:[];
          note.textContent=overlaps.length
            ? "Trùng với: "+overlaps.join(", ")+". Giờ hiện tại: "+textDate(task.study_at)
            : "Giờ hiện tại: "+textDate(task.study_at);
          suggestion.hidden=!task.suggested_at;
          if (task.suggested_at) {
            suggestion.textContent="Dùng giờ trống gợi ý: "+textDate(task.suggested_at);
            suggestion.dataset.at=task.suggested_at;
          }
        }
        selector.addEventListener("change",chooseTask);
        time.addEventListener("input",resetProposal);
        suggestion.addEventListener("click",()=>{
          if (!suggestion.dataset.at) return;
          time.value=suggestion.dataset.at;
          resetProposal();
        });
        preview.addEventListener("click",async()=>{
          const task=selectedTask();
          if(!task||!time.value) {result.textContent="Vui lòng chọn giờ mới.";return;}
          resetProposal();
          preview.disabled=true;
          result.textContent="Đang kiểm tra giờ trống...";
          const requestedTime=time.value;
          const requestedTask=task.id;
          try {
            const value=await post("/api/chat/schedule/preview",data.csrf_token,{
              conversation_id:conversation,task_id:requestedTask,study_at:requestedTime
            });
            if(card!==active || time.value!==requestedTime ||
               selectedTask()?.id!==requestedTask) return;
            proposal=value;
            result.textContent="Từ "+textDate(value.old_study_at)+" → "+
              textDate(value.new_study_at)+". Chưa lưu lịch.";
            confirm.hidden=false;
          } catch (error) {
            if(card!==active) return;
            result.textContent=error.message;
            if(error.suggested_at) {
              suggestion.hidden=false;
              suggestion.dataset.at=error.suggested_at;
              suggestion.textContent="Dùng giờ trống gợi ý: "+
                textDate(error.suggested_at);
            }
          } finally { preview.disabled=false; }
        });
        confirm.addEventListener("click",async()=>{
          if(!proposal||confirm.disabled) return;
          if (proposal.new_study_at!==time.value ||
              Number(proposal.task_id)!==selectedTask()?.id) {
            resetProposal();
            result.textContent="Giờ học đã thay đổi. Vui lòng xem trước lại.";
            return;
          }
          confirm.disabled=true;
          try {
            const saved=await post("/api/chat/schedule/confirm",data.csrf_token,{
              conversation_id:conversation,proposal_id:proposal.proposal_id
            });
            if(card!==active) return;
            reset();
            appendMessage("assistant","✓ Đã đổi lịch “"+saved.title+"” từ "+
              textDate(saved.old_study_at)+" sang "+textDate(saved.study_at)+
              ". Lịch học đã được cập nhật; các buổi khác được giữ nguyên.");
            setStatus("Đã cập nhật lịch học");
          } catch(error) {
            if(card!==active) return;
            resetProposal();
            result.textContent=error.message+" Hãy kiểm tra lại giờ trước khi lưu.";
            setStatus("Chưa đổi lịch");
          } finally {confirm.disabled=false;}
        });
        chooseTask();
        messages.appendChild(card);messages.scrollTop=messages.scrollHeight;
        setStatus("Đã kiểm tra lịch");
      } catch(error) {
        appendMessage("error",error.message);
        setStatus("Không kiểm tra được lịch");
      } finally {
        pending=false;
        if(actionButton) actionButton.disabled=false;
      }
    }
    actionButton?.addEventListener("click",open);
    return {open, reset, isRequest};
  }
  return {attach,isRequest};
})();

/* Conversational Support: never mutate the timetable from plain model text.
   Server interprets constrained requests, validates preview and requires
   explicit confirmation. All rendered text is textContent (not innerHTML). */
window.FloatingAiSupport = (function () {
  "use strict";

  function attach({results, setStatus}) {
    const form=document.getElementById("floatingAiSupportForm");
    const input=document.getElementById("floatingAiSupportInput");
    const sendButton=document.getElementById("floatingAiSupportSend");
    const status=document.getElementById("floatingAiSupportStatus");
    const reviewButton=document.getElementById("floatingAiScheduleButton");
    if(!results||!form||!input) return {ready:Promise.resolve()};

    let csrf="", busy=false, generation=0, courses=[], conversations=[];
    const el=(tag,klass,value)=>{
      const node=document.createElement(tag);
      if(klass) node.className=klass;
      if(value!==undefined) node.textContent=String(value);
      return node;
    };
    const date=(iso)=>iso && iso.length>=16
      ? iso.slice(8,10)+"/"+iso.slice(5,7)+"/"+iso.slice(0,4)+" · "+iso.slice(11,16)
      : "Chưa có giờ";
    const setBusy=(state,label)=>{
      busy=state; input.disabled=state; sendButton.disabled=state;
      status.textContent=label|| (state?"Đang xử lý...":"Sẵn sàng");
      if(setStatus) setStatus(state?"AI Hỗ trợ đang xử lý":"Sẵn sàng");
    };
    async function api(url,options={}){
      const response=await fetch(url,{credentials:"same-origin",...options});
      const data=await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(data.error||"Yêu cầu chưa thực hiện được.");
      return data;
    }
    function post(url,body){
      return api(url,{method:"POST",headers:{"Content-Type":"application/json",
        "X-CSRF-Token":csrf},body:JSON.stringify(body)});
    }
    function scroll(){results.scrollTop=results.scrollHeight;}
    function bubble(role,message){
      results.querySelector(".floating-ai-support-empty")?.remove();
      const item=el("article","floating-ai-support-message "+role);
      item.append(el("strong",null,role==="user"?"Bạn":role==="error"?"Thông báo":"AI Study Agent"),
                  el("div","floating-ai-support-message-body",message));
      results.append(item);scroll();
      return item;
    }
    function card(title){
      const box=el("section","floating-ai-support-card");
      box.append(el("strong","floating-ai-support-card-heading",title));
      results.append(box);scroll();
      return box;
    }
    function line(parent,key,value){
      const row=el("div","floating-ai-support-row");
      row.append(el("span",null,key),el("strong",null,value));
      parent.append(row);
    }
    function button(text){
      const node=el("button","floating-ai-support-primary",text);
      node.type="button";
      return node;
    }
    function error(parent,reason){
      parent.append(el("p","floating-ai-review-warning",reason));
      scroll();
    }
    async function load(){
      try {
        const data=await api("/api/chat/support");
        csrf=data.csrf_token;
        courses=data.subjects||[];
        results.replaceChildren();
        const history=data.messages||[];
        if(!history.length) bubble("assistant","Tui có thể rà soát lịch, đổi giờ và tạo buổi tự học. Bạn muốn làm gì?");
        else history.forEach(m=>bubble(m.role==="user"?"user":"assistant",m.content));
        status.textContent="Sẵn sàng";
      } catch(e) {
        bubble("error",e.message);
        status.textContent="Chưa kết nối";
      }
    }
    async function getConversation(subjectId){
      if(!conversations.length) conversations=await api("/api/chats");
      return conversations.find(c=>Number(c.subject_id)===Number(subjectId));
    }
    async function review(){
      const data=await api("/api/chat/schedule/review");
      csrf=data.csrf_token||csrf;
      bubble("assistant",data.conflict_count
        ?"Có "+data.conflict_count+" buổi đang trùng giờ trong "+data.checked_count+" buổi sắp tới."
        :"Đã rà soát "+data.checked_count+" buổi. Không phát hiện lịch trùng.");
      if(!data.next_conflict) return;
      const task=data.next_conflict;
      const block=card("Đề xuất xử lý trùng giờ");
      line(block,"Buổi học",task.subject_name+" · "+task.title);
      line(block,"Đang xếp",date(task.study_at));
      if(task.conflict_titles?.length) error(block,"Trùng với: "+task.conflict_titles.join(", "));
      if(!task.suggested_at) {error(block,"Chưa tìm thấy giờ trống phù hợp.");return;}
      line(block,"Đề xuất",date(task.suggested_at));
      const preview=button("Xem trước việc đổi giờ");
      block.append(preview);
      preview.addEventListener("click",async()=>{
        preview.disabled=true;
        try{
          const result=await post("/api/chat/schedule/preview",{
            conversation_id:task.conversation_id,task_id:task.id,study_at:task.suggested_at
          });
          renderMoveConfirm(block,result,task.conversation_id);
          preview.remove();
        }catch(e){error(block,e.message);preview.disabled=false;}
      });
    }
    function renderMoveConfirm(parent,proposal,conversationId){
      const cardNode=el("div","floating-ai-support-confirm");
      line(cardNode,"Từ",date(proposal.old_study_at));
      line(cardNode,"Sang",date(proposal.new_study_at));
      cardNode.append(el("p","floating-ai-support-hint",
        "Chưa thay đổi lịch. Bấm xác nhận mới thực hiện."));
      const accept=button("✓ Xác nhận đổi lịch");
      const feedback=el("p","floating-ai-support-feedback");
      cardNode.append(accept,feedback);parent.append(cardNode);scroll();
      accept.addEventListener("click",async()=>{
        accept.disabled=true;
        try{
          const result=await post("/api/chat/schedule/confirm",{
            proposal_id:proposal.proposal_id,conversation_id:conversationId
          });
          feedback.textContent="✓ Đã chuyển “"+result.title+"” sang "+date(result.study_at)+".";
          bubble("assistant",feedback.textContent);
        }catch(e){feedback.textContent=e.message+" Lịch chưa thay đổi."; }
      });
    }
    async function reschedule(data){
      const block=card("Đổi giờ buổi học");
      const select=el("select","floating-ai-support-select");
      for(const t of data.candidates||[]){
        const subject=courses.find(s=>Number(s.id)===Number(t.subject_id));
        const option=el("option",null,(subject?.name||"Môn học")+" · "+t.title+" · "+date(t.study_at));
        option.value=String(t.id);select.append(option);
      }
      block.append(el("label","floating-ai-support-hint","Chọn đúng buổi học cần đổi"),select);
      line(block,"Giờ muốn chuyển tới",date(data.study_at));
      const preview=button("Xem trước đổi lịch");block.append(preview);
      preview.addEventListener("click",async()=>{
        preview.disabled=true;
        const chosen=(data.candidates||[]).find(c=>String(c.id)===select.value);
        try{
          const conversation=await getConversation(chosen.subject_id);
          if(!conversation)throw Error("Chưa có cuộc trò chuyện của môn này.");
          const p=await post("/api/chat/schedule/preview",{
            conversation_id:conversation.id,task_id:chosen.id,study_at:data.study_at
          });
          renderMoveConfirm(block,p,conversation.id);
          preview.remove();select.disabled=true;
        }catch(e){error(block,e.message);preview.disabled=false;}
      });
    }
    async function create(data){
      const block=card("Xác nhận buổi tự học");
      const topicInput=el("input","floating-ai-support-select");
      topicInput.value=data.topic;topicInput.maxLength=90;
      const when=el("input","floating-ai-support-select");
      when.type="datetime-local";when.value=data.study_at;when.required=true;
      const minutes=el("select","floating-ai-support-select");
      for(const n of [30,45,60,90,120]){
        const opt=el("option",null,n+" phút");opt.value=String(n);
        if(n===data.duration)opt.selected=true;minutes.append(opt);
      }
      const label=(name,node)=>{
        const l=el("label","floating-ai-support-field");
        l.append(el("span",null,name),node);block.append(l);
      };
      label("Nội dung",topicInput);
      label("Thời gian",when);
      label("Thời lượng",minutes);
      const documents=el("select","floating-ai-support-select");
      const uploadInput=el("input","floating-ai-support-upload");
      uploadInput.type="file";uploadInput.accept=".pdf,.docx,.txt,.md";
      const docsLine=el("p","floating-ai-support-hint",
        "Có thể chọn tài liệu có sẵn, tải file mới hoặc để trống.");
      const docsWrap=el("div","floating-ai-support-field");
      docsWrap.append(el("span",null,"Tài liệu cá nhân (tùy chọn)"),
                      documents,uploadInput,docsLine);
      block.append(docsWrap);
      async function refreshDocs(selected){
        const dataDocs=await api("/api/chat/support/documents"
          +(data.subject_id?"?subject_id="+encodeURIComponent(data.subject_id):""));
        documents.replaceChildren();
        const none=el("option",null,"Không gắn tài liệu");none.value="";
        documents.append(none);
        for(const doc of dataDocs.documents||[]){
          const opt=el("option",null,doc.original_name);opt.value=String(doc.id);
          documents.append(opt);
        }
        if(selected)documents.value=String(selected);
      }
      try{await refreshDocs();}catch(e){error(block,e.message);}
      const uploadButton=button("↑ Tải file mới và chọn cho buổi này");
      uploadButton.classList.add("floating-ai-support-secondary");
      block.append(uploadButton);
      uploadButton.addEventListener("click",async()=>{
        if(!uploadInput.files?.length){error(block,"Hãy chọn một file trước.");return;}
        uploadButton.disabled=true;
        const formData=new FormData();
        formData.append("file",uploadInput.files[0]);
        if(data.subject_id)formData.append("subject_id",data.subject_id);
        try{
          const uploaded=await api("/api/chat/support/upload",{
            method:"POST",headers:{"X-CSRF-Token":csrf},body:formData
          });
          await refreshDocs(uploaded.document.id);
          docsLine.textContent="✓ Đã tải file. File sẽ được gắn khi bạn xác nhận tạo buổi học.";
          uploadInput.value="";
        }catch(e){error(block,e.message);}
        finally{uploadButton.disabled=false;}
      });
      const warning=el("p","floating-ai-support-hint",
        "Chủ nhật mặc định nghỉ; chỉ thêm lịch Chủ nhật nếu bạn chủ động xác nhận.");
      warning.hidden=!data.sunday;
      block.append(warning);
      const preview=button("Xem trước buổi học");
      block.append(preview);
      preview.addEventListener("click",async()=>{
        preview.disabled=true;
        try{
          const proposal=await post("/api/chat/support/create/preview",{
            topic:topicInput.value,subject_id:data.subject_id,study_at:when.value,
            duration:Number(minutes.value),document_id:documents.value||null
          });
          const confirmation=el("div","floating-ai-support-confirm");
          line(confirmation,"Nội dung",proposal.title);
          line(confirmation,"Thời gian",date(proposal.study_at));
          line(confirmation,"Thời lượng",proposal.duration+" phút");
          if(proposal.sunday)error(confirmation,"Chủ nhật là ngày nghỉ mặc định; bạn đang tự chọn học ngày này.");
          if(proposal.outside_evening)error(confirmation,"Buổi tự học nằm ngoài khung tối 19:00–22:00.");
          confirmation.append(el("p","floating-ai-support-hint",
            "Chưa tạo lịch. Bấm xác nhận để lưu lịch và gắn tài liệu."));
          const accept=button("✓ Xác nhận thêm buổi tự học");
          const feedback=el("p","floating-ai-support-feedback");
          confirmation.append(accept,feedback);block.append(confirmation);
          topicInput.disabled=true;when.disabled=true;minutes.disabled=true;
          documents.disabled=true;uploadInput.disabled=true;uploadButton.disabled=true;
          preview.remove();scroll();
          accept.addEventListener("click",async()=>{
            accept.disabled=true;
            try{
              const saved=await post("/api/chat/support/create/confirm",
                {proposal_id:proposal.proposal_id});
              feedback.textContent="✓ Đã tạo “"+saved.title+"” lúc "+date(saved.study_at)+".";
              bubble("assistant",feedback.textContent);
            }catch(e){feedback.textContent=e.message+" Buổi học chưa được tạo.";}
          });
        }catch(e){error(block,e.message);preview.disabled=false;}
      });
    }
    async function send(text){
      if(busy||!csrf||!String(text||"").trim())return;
      const msg=String(text).trim();
      setBusy(true,"Đang đọc yêu cầu...");
      bubble("user",msg);
      try{
        const data=await post("/api/chat/support/message",{message:msg});
        bubble("assistant",data.reply);
        if(data.intent==="review")await review();
        if(data.intent==="reschedule")await reschedule(data);
        if(data.intent==="create")await create(data);
      }catch(e){bubble("error",e.message);}
      finally{setBusy(false);}
    }
    form.addEventListener("submit",e=>{
      e.preventDefault();const value=input.value.trim();input.value="";
      send(value);
    });
    reviewButton?.addEventListener("click",()=>send("Rà soát có buổi học nào trùng không?"));
    document.querySelectorAll("[data-support-suggestion]").forEach(b=>{
      b.addEventListener("click",()=>send(b.dataset.supportSuggestion));
    });
    return {ready:load(),send};
  }
  return {attach};
})();

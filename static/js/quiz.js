document.addEventListener("DOMContentLoaded", () => {
  const quizCards = document.querySelectorAll(".quiz-card");

  const deleteQuizModal = document.getElementById("deleteQuizModal");
  const deleteQuizText = document.getElementById("deleteQuizText");
  const deleteQuizForm = document.getElementById("deleteQuizForm");
  const cancelDeleteQuiz = document.getElementById("cancelDeleteQuiz");
  const createHub = document.getElementById("quizCreateModes");
  const createModeTabs = Array.from(
    createHub?.querySelectorAll("[data-create-mode]") || []
  );
  const createModePanels = Array.from(
    createHub?.querySelectorAll("[data-create-panel]") || []
  );

  function activateCreateMode(mode) {
    const validMode = createModePanels.some(
      panel => panel.dataset.createPanel === mode
    ) ? mode : "subject";

    createModeTabs.forEach(tab => {
      const active = tab.dataset.createMode === validMode;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });

    createModePanels.forEach(panel => {
      panel.hidden = panel.dataset.createPanel !== validMode;
    });
  }

  createModeTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      activateCreateMode(tab.dataset.createMode || "subject");
    });
  });

  if (createHub) {
    activateCreateMode(createHub.dataset.initialMode || "subject");
  }


  // =====================================================
  // MODAL XÓA QUIZ
  // =====================================================

  function closeDeleteQuizModal() {
    deleteQuizModal?.classList.remove("show");
    document.body.classList.remove("modal-open");
  }

  document.querySelectorAll(".quiz-delete-btn").forEach(button => {
    button.addEventListener("click", event => {
      event.stopPropagation();

      const deleteUrl = button.dataset.deleteUrl || "";
      const quizTitle = button.dataset.quizTitle || "quiz này";

      if (deleteQuizText) {
        deleteQuizText.textContent =
          `Bạn có chắc muốn xóa “${quizTitle}” không? Hành động này không thể hoàn tác.`;
      }

      if (deleteQuizForm) {
        deleteQuizForm.action = deleteUrl;
      }

      deleteQuizModal?.classList.add("show");
      document.body.classList.add("modal-open");
    });
  });

  cancelDeleteQuiz?.addEventListener("click", closeDeleteQuizModal);

  deleteQuizModal?.addEventListener("click", event => {
    if (event.target === deleteQuizModal) {
      closeDeleteQuizModal();
    }
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && deleteQuizModal?.classList.contains("show")) {
      closeDeleteQuizModal();
    }
  });

  // =====================================================
  // BỘ LỌC DANH SÁCH QUIZ
  // =====================================================
  const filterButtons = document.querySelectorAll("[data-quiz-filter]");
  const pickerButtons = Array.from(document.querySelectorAll(".quiz-picker"));

  function applyQuizFilter(mode) {
    let firstVisible = null;

    pickerButtons.forEach(button => {
      const attempted = button.dataset.attempted === "true";
      const recentRank = Number(button.dataset.recentRank || 999);
      const visible =
        mode === "done" ? attempted :
        mode === "recent" ? recentRank <= 5 :
        true;

      button.hidden = !visible;
      if (visible && !firstVisible) firstVisible = button;
    });

    const activePicker = pickerButtons.find(
      button => !button.hidden && button.classList.contains("active")
    );

    if (!activePicker && firstVisible) {
      firstVisible.click();
    }

    if (!firstVisible) {
      document.querySelectorAll(".quiz-card").forEach(card => {
        card.classList.remove("active-workspace");
      });
    }
  }

  filterButtons.forEach(button => {
    button.addEventListener("click", () => {
      filterButtons.forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      applyQuizFilter(button.dataset.quizFilter || "all");
    });
  });

  // =====================================================
  // TỪNG QUIZ
  // =====================================================

  quizCards.forEach(quizCard => {
    const questions = quizCard.querySelectorAll(".quiz-question-card");
    const progressText = quizCard.querySelector(".quiz-progress-text");
    const progressBar = quizCard.querySelector(".quiz-progress-bar span");
    const resultBox = quizCard.querySelector(".quiz-result");
    const resultTitle = quizCard.querySelector(".quiz-result-title");
    const resultText = quizCard.querySelector(".quiz-result-text");
    const submitBtn = quizCard.querySelector(".quiz-submit-btn");
    const resetBtn = quizCard.querySelector(".quiz-reset-btn");
    const toggleBtn = quizCard.querySelector(".quiz-toggle");

    let submitted = false;

    // -----------------------------------------------------
    // THU GỌN / MỞ QUIZ
    // -----------------------------------------------------
    toggleBtn?.addEventListener("click", () => {
      quizCard.classList.toggle("collapsed");
    });

    // -----------------------------------------------------
    // TIẾN ĐỘ
    // -----------------------------------------------------
    function updateProgress() {
      let answered = 0;

      questions.forEach(question => {
        const selected = question.querySelector('input[type="radio"]:checked');
        if (selected) answered++;
      });

      const total = questions.length;
      const percentage = total > 0 ? (answered / total) * 100 : 0;

      if (progressText) {
        progressText.textContent = `${answered} / ${total} câu`;
      }

      if (progressBar) {
        progressBar.style.width = `${percentage}%`;
      }
    }

    // -----------------------------------------------------
    // CHỌN ĐÁP ÁN
    // -----------------------------------------------------
    questions.forEach(question => {
      question.querySelectorAll('input[type="radio"]').forEach(radio => {
        radio.addEventListener("change", () => {
          if (submitted) return;

          question.querySelectorAll(".quiz-option").forEach(option => {
            option.classList.remove("selected");
          });

          radio.closest(".quiz-option")?.classList.add("selected");
          updateProgress();
        });
      });
    });

    // -----------------------------------------------------
    // BOOKMARK
    // -----------------------------------------------------
    quizCard.querySelectorAll(".question-bookmark").forEach(button => {
      button.addEventListener("click", () => {
        button.classList.toggle("active");
        button.textContent = button.classList.contains("active") ? "♥" : "♡";
      });
    });

    // -----------------------------------------------------
    // NỘP BÀI + LƯU KẾT QUẢ VÀO SQLITE
    // -----------------------------------------------------
    submitBtn?.addEventListener("click", async () => {
      if (submitted) return;

      const quizId = Number(quizCard.dataset.quizId);
      const answers = [];
      let answered = 0;

      questions.forEach(question => {
        const selected = question.querySelector('input[type="radio"]:checked');

        if (selected) {
          answered++;
          answers.push(Number(selected.value));
        } else {
          answers.push(null);
        }
      });

      if (!Number.isInteger(quizId) || quizId <= 0) {
        resultBox?.classList.add("show");
        if (resultTitle) resultTitle.textContent = "Không thể nộp bài";
        if (resultText) resultText.textContent = "Không xác định được Quiz. Hãy tải lại trang rồi thử lại.";
        return;
      }

      if (answered < questions.length) {
        const wantSubmit = confirm(
          `Bạn mới làm ${answered}/${questions.length} câu. Bạn vẫn muốn nộp bài?`
        );

        if (!wantSubmit) return;
      }

      const oldSubmitText = submitBtn.textContent;
      submitBtn.disabled = true;
      submitBtn.textContent = "Đang lưu...";

      try {
        const response = await fetch("/api/quiz/submit", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            quiz_id: quizId,
            answers: answers
          })
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error || "Không thể lưu kết quả Quiz.");
        }

        submitted = true;

        const picker = document.querySelector(
          `.quiz-picker[data-quiz-target="${quizCard.id}"]`
        );
        if (picker) {
          picker.dataset.attempted = "true";

          const pickerMeta = picker.querySelector("small");
          if (pickerMeta) {
            const bestScore = Math.round(Number(data.best_score ?? data.score ?? 0));
            pickerMeta.textContent =
              `${questions.length} câu hỏi · Đã làm · Cao nhất ${bestScore}%`;
          }
        }

        // Cập nhật ngay danh sách "Ôn tập điểm yếu" mà không cần reload trang.
        const weaknessForm = document
          .querySelector('.quiz-create-mode input[name="quiz_mode"][value="weakness"]')
          ?.closest("form");
        const weaknessSelect = weaknessForm?.querySelector('select[name="subject_id"]');

        if (
          weaknessSelect &&
          Number(data.subject_id) > 0 &&
          Number(data.weakness_count) > 0
        ) {
          const subjectId = String(data.subject_id);
          let option = Array.from(weaknessSelect.options).find(
            item => item.value === subjectId
          );

          if (!option) {
            option = document.createElement("option");
            option.value = subjectId;
            weaknessSelect.appendChild(option);
          }

          option.textContent =
            `${data.subject_name || "Môn học"} · ${data.weakness_count} chủ đề cần ôn`;
        }

        // Chấm và khóa đáp án trên giao diện
        questions.forEach(question => {
          const correctAnswer = Number(question.dataset.answer);
          const selected = question.querySelector('input[type="radio"]:checked');
          const options = question.querySelectorAll(".quiz-option");

          const correctOption = options[correctAnswer];
          correctOption?.classList.add("correct");

          const correctIcon = correctOption?.querySelector(".option-result-icon");
          if (correctIcon) correctIcon.textContent = "✓";

          if (selected) {
            const selectedIndex = Number(selected.value);
            const selectedOption = selected.closest(".quiz-option");

            if (selectedIndex !== correctAnswer) {
              selectedOption?.classList.add("wrong");

              const wrongIcon = selectedOption?.querySelector(".option-result-icon");
              if (wrongIcon) wrongIcon.textContent = "✕";
            }
          } else {
            question.classList.add("unanswered");
          }

          question.querySelectorAll('input[type="radio"]').forEach(radio => {
            radio.disabled = true;
          });
        });

        const score = Number(data.score || 0);
        const correctCount = Number(data.correct_count || 0);
        const totalQuestions = Number(data.total_questions || questions.length);

        resultBox?.classList.add("show");

        if (resultTitle) {
          resultTitle.textContent = `${correctCount}/${totalQuestions} câu đúng`;
        }

        if (resultText) {
          if (score >= 80) {
            resultText.textContent = `Rất tốt! Bạn đạt ${score}%. Kết quả đã được lưu.`;
          } else if (score >= 50) {
            resultText.textContent = `Bạn đạt ${score}%. Hãy xem lại những câu sai nhé. Kết quả đã được lưu.`;
          } else {
            resultText.textContent = `Bạn đạt ${score}%. Nên ôn lại tài liệu và thử lại. Kết quả đã được lưu.`;
          }

          if (data.learning_updated) {
            const weaknessCount = Number(data.weakness_count || 0);
            resultText.textContent += weaknessCount > 0
              ? ` Study Agent đã cập nhật ${weaknessCount} chủ đề cần ôn.`
              : " Study Agent đã cập nhật hồ sơ học tập từ kết quả này.";
          }
        }

        if (progressText) progressText.textContent = "Đã hoàn thành";
        if (progressBar) progressBar.style.width = "100%";

        resultBox?.scrollIntoView({
          behavior: "smooth",
          block: "nearest"
        });

      } catch (error) {
        console.error("Lỗi lưu kết quả Quiz:", error);

        resultBox?.classList.add("show");
        if (resultTitle) resultTitle.textContent = "Chưa lưu được kết quả";
        if (resultText) {
          resultText.textContent =
            error.message || "Có lỗi khi lưu kết quả. Bạn hãy thử nộp lại.";
        }
      } finally {
        submitBtn.disabled = submitted;
        submitBtn.textContent = submitted ? "✓ Đã nộp" : oldSubmitText;
      }
    });

    // -----------------------------------------------------
    // LÀM LẠI
    // -----------------------------------------------------
    resetBtn?.addEventListener("click", () => {
      submitted = false;

      questions.forEach(question => {
        question.classList.remove("unanswered");

        question.querySelectorAll('input[type="radio"]').forEach(radio => {
          radio.checked = false;
          radio.disabled = false;
        });

        question.querySelectorAll(".quiz-option").forEach(option => {
          option.classList.remove("selected", "correct", "wrong");

          const icon = option.querySelector(".option-result-icon");
          if (icon) icon.textContent = "";
        });
      });

      resultBox?.classList.remove("show");

      if (resultTitle) resultTitle.textContent = "Kết quả";
      if (resultText) resultText.textContent = "Bạn chưa nộp bài.";

      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "✓ Nộp bài";
      }

      updateProgress();
    });

    updateProgress();
  });
});
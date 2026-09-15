const loginForm = document.getElementById("loginForm");
    const signupForm = document.getElementById("signupForm");

    const loginMessage = document.getElementById("loginMessage");
    const signupMessage = document.getElementById("signupMessage");

    const loginEmail = document.getElementById("loginEmail");
    const loginPassword = document.getElementById("loginPassword");

    const firstName = document.getElementById("firstName");
    const lastName = document.getElementById("lastName");
    const signupEmail = document.getElementById("signupEmail");
    const signupPassword = document.getElementById("signupPassword");
    const confirmPassword = document.getElementById("confirmPassword");
    const termsCheck = document.getElementById("termsCheck");

    function isValidEmail(email){
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function resetInputs(inputs){
      inputs.forEach(input=>{
        input.classList.remove("error","success");
      });
    }

    function setInputState(input, state){
      input.classList.remove("error","success");
      if(state) input.classList.add(state);
    }

    function showMessage(box, type, title, text){
      box.className = "message " + type + " show";
      box.querySelector(".icon").textContent = type === "success" ? "✓" : "!";
      box.querySelector("strong").textContent = title;
      box.querySelector("span").textContent = text;
    }

    /* LOGIN VALIDATION */
    loginForm.addEventListener("submit", function(e){
      e.preventDefault();

      const inputs = [loginEmail, loginPassword];
      resetInputs(inputs);

      let valid = true;

      if(loginEmail.value.trim() === ""){
        setInputState(loginEmail, "error");
        valid = false;
      }else if(!isValidEmail(loginEmail.value.trim())){
        setInputState(loginEmail, "error");
        valid = false;
      }else{
        setInputState(loginEmail, "success");
      }

      if(loginPassword.value.trim() === ""){
        setInputState(loginPassword, "error");
        valid = false;
      }else if(loginPassword.value.trim().length < 6){
        setInputState(loginPassword, "error");
        valid = false;
      }else{
        setInputState(loginPassword, "success");
      }

      if(!valid){
        showMessage(
          loginMessage,
          "error",
          "Login Failed",
          "Please enter a valid email and a password with at least 6 characters."
        );
      }else{
        showMessage(
          loginMessage,
          "success",
          "Login Successful",
          "Welcome back! Your login validation has been completed successfully."
        );
        loginForm.reset();
        setTimeout(()=>resetInputs(inputs),300);
      }
    });

    /* SIGNUP VALIDATION */
    signupForm.addEventListener("submit", function(e){
      e.preventDefault();

      const inputs = [firstName, lastName, signupEmail, signupPassword, confirmPassword];
      resetInputs(inputs);

      let valid = true;

      if(firstName.value.trim() === ""){
        setInputState(firstName, "error");
        valid = false;
      }else{
        setInputState(firstName, "success");
      }

      if(lastName.value.trim() === ""){
        setInputState(lastName, "error");
        valid = false;
      }else{
        setInputState(lastName, "success");
      }

      if(signupEmail.value.trim() === "" || !isValidEmail(signupEmail.value.trim())){
        setInputState(signupEmail, "error");
        valid = false;
      }else{
        setInputState(signupEmail, "success");
      }

      if(signupPassword.value.trim().length < 6){
        setInputState(signupPassword, "error");
        valid = false;
      }else{
        setInputState(signupPassword, "success");
      }

      if(confirmPassword.value.trim() === "" || confirmPassword.value !== signupPassword.value){
        setInputState(confirmPassword, "error");
        valid = false;
      }else{
        setInputState(confirmPassword, "success");
      }

      if(!termsCheck.checked){
        valid = false;
      }

      if(!valid){
        showMessage(
          signupMessage,
          "error",
          "Sign Up Failed",
          "Please fill all fields correctly, match passwords, and accept the terms & conditions."
        );
      }else{
        showMessage(
          signupMessage,
          "success",
          "Account Created",
          "Your account has been created successfully. You can now sign in."
        );
        signupForm.reset();
        setTimeout(()=>resetInputs(inputs),300);
      }
    });
      
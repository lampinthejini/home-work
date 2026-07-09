const authSection = document.getElementById("authSection");
const appSection = document.getElementById("appSection");

const authError = document.getElementById("authError");
const authUsername = document.getElementById("authUsername");
const authPassword = document.getElementById("authPassword");
const authPasswordConfirm = document.getElementById("authPasswordConfirm");
const signupOnlyFields = document.getElementById("signupOnlyFields");
const loginButton = document.getElementById("loginButton");
const signupButton = document.getElementById("signupButton");
const toggleModeLink = document.getElementById("toggleModeLink");
const toggleModeText = document.getElementById("toggleModeText");

const currentUsernameEl = document.getElementById("currentUsername");
const logoutButton = document.getElementById("logoutButton");
const signupSuccessMessage = document.getElementById("signupSuccessMessage");

const contactFormTitle = document.getElementById("contactFormTitle");
const contactFormError = document.getElementById("contactFormError");
const contactSuccessMessage = document.getElementById("contactSuccessMessage");
const contactName = document.getElementById("contactName");
const contactPhone = document.getElementById("contactPhone");
const contactAddr = document.getElementById("contactAddr");
const contactCategory = document.getElementById("contactCategory");
const contactSubmitButton = document.getElementById("contactSubmitButton");
const contactCancelButton = document.getElementById("contactCancelButton");
const contactEditingId = document.getElementById("contactEditingId");

const searchName = document.getElementById("searchName");
const searchButton = document.getElementById("searchButton");
const searchResetButton = document.getElementById("searchResetButton");

const contactTotal = document.getElementById("contactTotal");
const contactTableBody = document.getElementById("contactTableBody");

const categoryError = document.getElementById("categoryError");
const categorySuccessMessage = document.getElementById("categorySuccessMessage");
const categoryList = document.getElementById("categoryList");
const newCategoryName = document.getElementById("newCategoryName");
const newCategoryButton = document.getElementById("newCategoryButton");

let isSignupMode = false;
let categories = [];
let editingCategoryId = null;

async function apiFetch(url, options) {
    const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        ...options,
    });

    if (response.status === 204) {
        return null;
    }

    const body = await response.json();

    if (!response.ok) {
        if (response.status === 401 && url !== "/auth/login" && !appSection.classList.contains("hidden")) {
            showAuthSection();
            authError.textContent = "다시 로그인해 주세요.";
        }
        const message = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
        throw new Error(message || "요청 처리 중 오류가 발생했습니다.");
    }

    return body;
}

function showTransientMessage(el, text) {
    el.textContent = text;
    el.classList.remove("hidden");
    setTimeout(() => {
        el.classList.add("hidden");
    }, 1500);
}

function setAuthMode(signup) {
    isSignupMode = signup;
    authError.textContent = "";
    signupOnlyFields.classList.toggle("hidden", !isSignupMode);
    loginButton.classList.toggle("hidden", isSignupMode);
    signupButton.classList.toggle("hidden", !isSignupMode);
    toggleModeText.textContent = isSignupMode ? "이미 계정이 있으신가요? " : "계정이 없으신가요? ";
    toggleModeText.appendChild(toggleModeLink);
    toggleModeLink.textContent = isSignupMode ? "로그인" : "회원가입";
}

function showAuthSection() {
    authSection.classList.remove("hidden");
    appSection.classList.add("hidden");
    setAuthMode(false);
}

function showAppSection(username) {
    authSection.classList.add("hidden");
    appSection.classList.remove("hidden");
    currentUsernameEl.textContent = username;
}

async function checkAuth() {
    try {
        const me = await apiFetch("/auth/me");
        showAppSection(me.username);
        await loadCategories();
        await loadContacts();
    } catch (err) {
        showAuthSection();
    }
}

toggleModeLink.addEventListener("click", (event) => {
    event.preventDefault();
    setAuthMode(!isSignupMode);
});

loginButton.addEventListener("click", async () => {
    authError.textContent = "";
    loginButton.disabled = true;
    try {
        await apiFetch("/auth/login", {
            method: "POST",
            body: JSON.stringify({
                username: authUsername.value,
                password: authPassword.value,
            }),
        });
        authPassword.value = "";
        await checkAuth();
    } catch (err) {
        authError.textContent = err.message;
    } finally {
        loginButton.disabled = false;
    }
});

signupButton.addEventListener("click", async () => {
    authError.textContent = "";
    if (authPassword.value !== authPasswordConfirm.value) {
        authError.textContent = "비밀번호가 일치하지 않습니다.";
        return;
    }
    const enteredUsername = authUsername.value;
    const enteredPassword = authPassword.value;
    signupButton.disabled = true;
    try {
        await apiFetch("/auth/signup", {
            method: "POST",
            body: JSON.stringify({
                username: enteredUsername,
                password: enteredPassword,
                password_confirm: authPasswordConfirm.value,
            }),
        });
        authPassword.value = "";
        authPasswordConfirm.value = "";
        await apiFetch("/auth/login", {
            method: "POST",
            body: JSON.stringify({
                username: enteredUsername,
                password: enteredPassword,
            }),
        });
        await checkAuth();
        showTransientMessage(signupSuccessMessage, "회원가입이 완료되었습니다! 환영합니다.");
    } catch (err) {
        authError.textContent = err.message;
    } finally {
        signupButton.disabled = false;
    }
});

logoutButton.addEventListener("click", async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    showAuthSection();
});

async function loadCategories() {
    categories = await apiFetch("/categories");
    renderCategoryDropdown();
    renderCategoryList();
}

function renderCategoryDropdown() {
    contactCategory.innerHTML = "";
    for (const category of categories) {
        const option = document.createElement("option");
        option.value = category.id;
        option.textContent = category.name;
        contactCategory.appendChild(option);
    }
}

function renderCategoryList() {
    categoryList.innerHTML = "";
    for (const category of categories) {
        const li = document.createElement("li");

        if (category.id === editingCategoryId) {
            const editInput = document.createElement("input");
            editInput.type = "text";
            editInput.value = category.name;

            const saveButton = document.createElement("button");
            saveButton.textContent = "저장";
            saveButton.classList.add("btnSave");
            saveButton.addEventListener("click", () => {
                saveButton.disabled = true;
                handleCategorySave(category, editInput.value).finally(() => {
                    saveButton.disabled = false;
                });
            });

            const cancelButton = document.createElement("button");
            cancelButton.textContent = "취소";
            cancelButton.classList.add("btnCancel");
            cancelButton.addEventListener("click", () => {
                editingCategoryId = null;
                renderCategoryList();
            });

            li.appendChild(editInput);
            li.appendChild(saveButton);
            li.appendChild(cancelButton);
        } else {
            const nameSpan = document.createElement("span");
            nameSpan.textContent = category.name;

            const editButton = document.createElement("button");
            editButton.textContent = "수정";
            editButton.classList.add("btnEdit");
            editButton.addEventListener("click", () => {
                editingCategoryId = category.id;
                renderCategoryList();
            });

            const deleteButton = document.createElement("button");
            deleteButton.textContent = "삭제";
            deleteButton.classList.add("btnDelete");
            deleteButton.addEventListener("click", () => handleCategoryDelete(category));

            li.appendChild(nameSpan);
            li.appendChild(editButton);
            li.appendChild(deleteButton);
        }

        categoryList.appendChild(li);
    }
}

async function handleCategorySave(category, newName) {
    categoryError.textContent = "";
    try {
        await apiFetch(`/categories/${category.id}`, {
            method: "PATCH",
            body: JSON.stringify({ name: newName }),
        });
        editingCategoryId = null;
        await loadCategories();
        await loadContacts();
        showTransientMessage(categorySuccessMessage, "수정되었습니다.");
    } catch (err) {
        categoryError.textContent = err.message;
    }
}

async function handleCategoryDelete(category) {
    if (!confirm("정말 삭제하시겠습니까?")) {
        return;
    }
    categoryError.textContent = "";
    try {
        await apiFetch(`/categories/${category.id}`, { method: "DELETE" });
        await loadCategories();
        showTransientMessage(categorySuccessMessage, "삭제되었습니다.");
    } catch (err) {
        categoryError.textContent = err.message;
    }
}

newCategoryButton.addEventListener("click", async () => {
    categoryError.textContent = "";
    newCategoryButton.disabled = true;
    try {
        await apiFetch("/categories", {
            method: "POST",
            body: JSON.stringify({ name: newCategoryName.value }),
        });
        newCategoryName.value = "";
        await loadCategories();
        showTransientMessage(categorySuccessMessage, "추가되었습니다.");
    } catch (err) {
        categoryError.textContent = err.message;
    } finally {
        newCategoryButton.disabled = false;
    }
});

async function loadContacts(name) {
    const query = name ? `?name=${encodeURIComponent(name)}` : "";
    const result = await apiFetch(`/contacts${query}`);
    renderContacts(result);
}

function renderContacts(result) {
    contactTotal.textContent = result.total;
    contactTableBody.innerHTML = "";

    for (const contact of result.items) {
        const row = document.createElement("tr");

        for (const value of [contact.name, contact.phone, contact.addr, contact.category_name]) {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);
        }

        const editCell = document.createElement("td");
        const editButton = document.createElement("button");
        editButton.textContent = "수정";
        editButton.classList.add("btnEdit");
        editButton.addEventListener("click", () => startContactEdit(contact));
        editCell.appendChild(editButton);
        row.appendChild(editCell);

        const deleteCell = document.createElement("td");
        const deleteButton = document.createElement("button");
        deleteButton.textContent = "삭제";
        deleteButton.classList.add("btnDelete");
        deleteButton.addEventListener("click", () => handleContactDelete(contact.id));
        deleteCell.appendChild(deleteButton);
        row.appendChild(deleteCell);

        contactTableBody.appendChild(row);
    }
}

function startContactEdit(contact) {
    contactFormTitle.textContent = "연락처 수정";
    contactEditingId.value = contact.id;
    contactName.value = contact.name;
    contactPhone.value = contact.phone;
    contactAddr.value = contact.addr;
    contactCategory.value = contact.category_id;
    contactSubmitButton.textContent = "수정 완료";
    contactCancelButton.classList.remove("hidden");
}

function resetContactForm() {
    contactFormTitle.textContent = "연락처 등록";
    contactEditingId.value = "";
    contactName.value = "";
    contactPhone.value = "";
    contactAddr.value = "";
    contactSubmitButton.textContent = "추가";
    contactCancelButton.classList.add("hidden");
}

contactCancelButton.addEventListener("click", resetContactForm);

contactSubmitButton.addEventListener("click", async () => {
    contactFormError.textContent = "";
    contactSubmitButton.disabled = true;

    const payload = {
        name: contactName.value,
        phone: contactPhone.value,
        addr: contactAddr.value,
        category_id: Number(contactCategory.value),
    };

    const isEditing = Boolean(contactEditingId.value);
    try {
        if (isEditing) {
            await apiFetch(`/contacts/${contactEditingId.value}`, {
                method: "PATCH",
                body: JSON.stringify(payload),
            });
        } else {
            await apiFetch("/contacts", {
                method: "POST",
                body: JSON.stringify(payload),
            });
        }
        resetContactForm();
        await loadContacts(searchName.value);
        showTransientMessage(contactSuccessMessage, isEditing ? "수정되었습니다." : "추가되었습니다.");
    } catch (err) {
        contactFormError.textContent = err.message;
    } finally {
        contactSubmitButton.disabled = false;
    }
});

async function handleContactDelete(contactId) {
    if (!confirm("정말 삭제하시겠습니까?")) {
        return;
    }
    contactFormError.textContent = "";
    try {
        await apiFetch(`/contacts/${contactId}`, { method: "DELETE" });
        await loadContacts(searchName.value);
        showTransientMessage(contactSuccessMessage, "삭제되었습니다.");
    } catch (err) {
        contactFormError.textContent = err.message;
    }
}

searchButton.addEventListener("click", () => loadContacts(searchName.value));
searchResetButton.addEventListener("click", () => {
    searchName.value = "";
    loadContacts();
});

checkAuth();

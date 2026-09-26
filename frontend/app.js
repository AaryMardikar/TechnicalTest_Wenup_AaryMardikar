const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const resetBtn = document.getElementById("resetBtn");
const docPreview = document.getElementById("docPreview");
const jsonPreview = document.getElementById("jsonPreview");

const tabDocBtn = document.getElementById("tabDocBtn");
const tabJsonBtn = document.getElementById("tabJsonBtn");
const viewDoc = document.getElementById("viewDoc");
const viewJson = document.getElementById("viewJson");

const DEFAULT_GREETING = "Hello! I am your intake assistant. I will collect your details to prepare your draft Personal Wishes Document. To start, what is your full legal name and current home address?";

// 1. Session Persistence Setup
let sessionId = localStorage.getItem("intake_session_id");
if (!sessionId) {
    sessionId = "session-" + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("intake_session_id", sessionId);
}

// 2. Tab Navigation
tabDocBtn.addEventListener("click", () => {
    tabDocBtn.className = "tab-active text-xs font-bold px-4 py-2.5 rounded-t-lg transition flex items-center space-x-2";
    tabJsonBtn.className = "tab-inactive text-xs font-bold px-4 py-2.5 rounded-t-lg transition flex items-center space-x-2";
    viewDoc.classList.remove("hidden");
    viewJson.classList.add("hidden");
});

tabJsonBtn.addEventListener("click", () => {
    tabJsonBtn.className = "tab-active text-xs font-bold px-4 py-2.5 rounded-t-lg transition flex items-center space-x-2";
    tabDocBtn.className = "tab-inactive text-xs font-bold px-4 py-2.5 rounded-t-lg transition flex items-center space-x-2";
    viewJson.classList.remove("hidden");
    viewDoc.classList.add("hidden");
});

// 3. Message Bubble Rendering
function appendMessage(role, text) {
    const wrapper = document.createElement("div");
    const isUser = role === "user";

    wrapper.className = isUser
        ? "flex items-start justify-end space-x-3"
        : "flex items-start space-x-3";

    const badge = document.createElement("div");
    badge.className = isUser
        ? "w-8 h-8 rounded-lg bg-yellow-300 text-slate-900 flex items-center justify-center text-xs font-bold shrink-0 shadow-sm order-2"
        : "w-8 h-8 rounded-lg bg-blue-700 text-yellow-300 flex items-center justify-center text-xs font-bold shrink-0 shadow-sm";
    badge.innerText = isUser ? "YOU" : "AI";

    const bubble = document.createElement("div");
    bubble.className = isUser
        ? "bg-blue-700 text-white p-3.5 rounded-2xl rounded-tr-sm max-w-[85%] text-sm leading-relaxed shadow-sm order-1"
        : "bg-slate-100 border border-slate-200 text-slate-800 p-3.5 rounded-2xl rounded-tl-sm max-w-[85%] text-sm leading-relaxed shadow-sm";
    bubble.innerText = text;

    wrapper.appendChild(badge);
    wrapper.appendChild(bubble);

    chatMessages.appendChild(wrapper);
    chatMessages.scrollTo({
        top: chatMessages.scrollHeight,
        behavior: "smooth"
    });
}

// 4. Instant Browser Cache Hydration
function hydrateFromCache() {
    const cachedDoc = localStorage.getItem("cached_doc_" + sessionId);
    const cachedJson = localStorage.getItem("cached_json_" + sessionId);
    const cachedHistory = localStorage.getItem("cached_history_" + sessionId);

    if (cachedDoc) docPreview.innerText = cachedDoc;
    if (cachedJson) jsonPreview.innerText = cachedJson;

    if (cachedHistory) {
        try {
            const history = JSON.parse(cachedHistory);
            if (Array.isArray(history) && history.length > 0) {
                chatMessages.innerHTML = "";
                appendMessage("assistant", DEFAULT_GREETING);
                history.forEach((msg) => appendMessage(msg.role, msg.content));
            }
        } catch (e) {
            console.error("Cache parsing error", e);
        }
    }
}

// 5. Fetch Backend State & Reconcile
async function fetchCurrentState() {
    try {
        const res = await fetch(`/api/state/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();

        docPreview.innerText = data.draft_document || "Waiting for information...";
        jsonPreview.innerText = JSON.stringify(data.state, null, 2);

        localStorage.setItem("cached_doc_" + sessionId, data.draft_document || "");
        localStorage.setItem("cached_json_" + sessionId, JSON.stringify(data.state, null, 2));
        localStorage.setItem("cached_history_" + sessionId, JSON.stringify(data.history || []));

        chatMessages.innerHTML = "";
        appendMessage("assistant", DEFAULT_GREETING);
        if (data.history && data.history.length > 0) {
            data.history.forEach((msg) => {
                appendMessage(msg.role, msg.content);
            });
        }
    } catch (err) {
        console.error("Failed to sync backend state", err);
    }
}

// 6. Send User Turn
chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = userInput.value.trim();
    if (!message) return;

    appendMessage("user", message);
    userInput.value = "";
    userInput.disabled = true;
    sendBtn.disabled = true;

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, message })
        });

        if (!response.ok) throw new Error("API request failed");

        const data = await response.json();
        appendMessage("assistant", data.assistant_reply);

        docPreview.innerText = data.draft_document;
        jsonPreview.innerText = JSON.stringify(data.state, null, 2);

        localStorage.setItem("cached_doc_" + sessionId, data.draft_document);
        localStorage.setItem("cached_json_" + sessionId, JSON.stringify(data.state, null, 2));

        fetchCurrentState();
    } catch (err) {
        appendMessage("assistant", "A temporary connection issue occurred. Your progress is preserved.");
    } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
});

// 7. Global Download Function
window.downloadDraft = function () {
    const docEl = document.getElementById("docPreview");
    let docText = docEl ? (docEl.innerText || docEl.textContent || "").trim() : "";

    // If DOM is still empty, retrieve directly from session storage
    if (!docText || docText === "Loading draft document..." || docText === "Waiting for information...") {
        const cached = localStorage.getItem("cached_doc_" + sessionId);
        if (cached) docText = cached.trim();
    }

    if (!docText || docText === "Loading draft document..." || docText === "Waiting for information...") {
        alert("No draft document is available to download yet. Please provide your details in the chat first.");
        return;
    }

    // Derive file name from the declarant's name if present
    const nameMatch = docText.match(/Full Name:\s+([^\r\n]+)/);
    let baseName = "Personal_Wishes_Draft";
    if (nameMatch && nameMatch[1] && !nameMatch[1].includes("[Pending Information]")) {
        baseName = nameMatch[1].trim().replace(/[^a-zA-Z0-9_-]/g, "_") + "_Personal_Wishes";
    }

    const dateStr = new Date().toISOString().split("T")[0];
    const filename = `${baseName}_${dateStr}.txt`;

    // Create download link
    const blob = new Blob([docText], { type: "text/plain;charset=utf-8" });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.style.display = "none";
    link.href = downloadUrl;
    link.download = filename;

    document.body.appendChild(link);
    link.click();

    setTimeout(() => {
        document.body.removeChild(link);
        URL.revokeObjectURL(downloadUrl);
    }, 250);
};

// 8. Restart Session Handler
resetBtn.addEventListener("click", async () => {
    if (confirm("Reset current intake session? This will start a fresh document.")) {
        localStorage.removeItem("cached_doc_" + sessionId);
        localStorage.removeItem("cached_json_" + sessionId);
        localStorage.removeItem("cached_history_" + sessionId);

        await fetch(`/api/reset/${sessionId}`, { method: "POST" });

        chatMessages.innerHTML = "";
        appendMessage("assistant", DEFAULT_GREETING);
        docPreview.innerText = "Waiting for information...";
        jsonPreview.innerText = "{}";
        fetchCurrentState();
    }
});

// Boot: Hydrate from cache then reconcile with server
hydrateFromCache();
fetchCurrentState();
console.log("✅ app.js loaded");

/* =========================
   Helpers: date formatting
========================= */
function pad(n) {
  return String(n).padStart(2, "0");
}

function formatDateTime(isoStr) {
  const d = new Date(isoStr);
  if (Number.isNaN(d.getTime())) return "";
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function updateDates() {
  document.querySelectorAll("[data-date]").forEach((el) => {
    const v = el.getAttribute("data-date");
    el.textContent = v ? formatDateTime(v) : "";
  });
}

/* =========================
   Countdown
========================= */
function updateCountdowns() {
  const now = new Date();

  document.querySelectorAll("[data-due]").forEach((el) => {
    const dueStr = el.getAttribute("data-due");
    if (!dueStr) return;

    const due = new Date(dueStr);
    if (Number.isNaN(due.getTime())) {
      el.textContent = "";
      return;
    }

    const diffMs = due - now;
    const totalMinutes = Math.floor(diffMs / (1000 * 60));

    const days = Math.floor(totalMinutes / (60 * 24));
    const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
    const mins = Math.abs(totalMinutes % 60);

    if (diffMs >= 0) {
      el.textContent = `بقات لك ${days} يوم و ${hours} س و ${mins} د`;
    } else {
      const late = Math.abs(totalMinutes);
      const ldays = Math.floor(late / (60 * 24));
      const lhours = Math.floor((late % (60 * 24)) / 60);
      const lmins = late % 60;
      el.textContent = `فات الأجل بـ ${ldays} يوم و ${lhours} س و ${lmins} د`;
    }
  });
}

/* =========================
   Mobile menu (burger)
========================= */
function initMobileMenu() {
  const nav = document.getElementById("siteNav");
  const burger = document.getElementById("burgerBtn");

  // إذا ماعندكش IDs فـ base.html، ما غاديش يدير والو
  if (!nav || !burger) return;

  function closeMenu() {
    nav.classList.remove("open");
    burger.setAttribute("aria-expanded", "false");
  }

  burger.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = nav.classList.toggle("open");
    burger.setAttribute("aria-expanded", open ? "true" : "false");
  });

  // click outside closes
  document.addEventListener("click", (e) => {
    if (!nav.contains(e.target) && !burger.contains(e.target)) closeMenu();
  });

  // click link closes
  nav.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", closeMenu);
  });

  // Esc closes
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenu();
  });
}

/* =========================
   Ratings popup + stars
========================= */
function initRatings() {
  const wraps = document.querySelectorAll("[data-rate-wrap]");
  if (!wraps.length) return;

  function closeAll(exceptPop = null) {
    document.querySelectorAll("[data-rate-pop]").forEach((p) => {
      if (p !== exceptPop) p.hidden = true;
    });
    document.querySelectorAll("[data-rate-open]").forEach((btn) => {
      btn.setAttribute("aria-expanded", "false");
    });
  }

  wraps.forEach((wrap) => {
    const openBtn = wrap.querySelector("[data-rate-open]");
    const pop = wrap.querySelector("[data-rate-pop]");
    const cancel = wrap.querySelector("[data-rate-cancel]");
    const okBtn = wrap.querySelector("[data-rate-ok]");
    const val = wrap.querySelector("[data-rate-value]");
    const stars = wrap.querySelectorAll("[data-star]");

    // إذا الكتاب Rated (زر disabled) => ماعندوش data-rate-open أصلاً
    if (!openBtn || !pop || !cancel || !okBtn || !val || stars.length === 0) return;

    function paint(n) {
      stars.forEach((s) => {
        const k = Number(s.getAttribute("data-star"));
        s.classList.toggle("on", k <= n);
      });
    }

    function openPop() {
      closeAll(pop);
      pop.hidden = false;
      openBtn.setAttribute("aria-expanded", "true");
    }

    function closePop() {
      pop.hidden = true;
      openBtn.setAttribute("aria-expanded", "false");
    }

    openBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (pop.hidden) openPop();
      else closePop();
    });

    cancel.addEventListener("click", (e) => {
      e.preventDefault();
      closePop();
    });

    stars.forEach((s) => {
      s.addEventListener("click", () => {
        const n = Number(s.getAttribute("data-star"));
        val.value = String(n);
        paint(n);
        okBtn.disabled = n <= 0;
      });
    });
  });

  // click outside closes any open popup
  document.addEventListener("click", (e) => {
    const anyOpen = document.querySelector("[data-rate-pop]:not([hidden])");
    if (!anyOpen) return;

    // إذا كليكاتي داخل wrapper ديال rate => خليه محلول
    if (e.target.closest("[data-rate-wrap]")) return;

    // وإلا سدو
    document.querySelectorAll("[data-rate-pop]").forEach((p) => (p.hidden = true));
    document.querySelectorAll("[data-rate-open]").forEach((btn) => btn.setAttribute("aria-expanded", "false"));
  });

  // Esc closes
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll("[data-rate-pop]").forEach((p) => (p.hidden = true));
    document.querySelectorAll("[data-rate-open]").forEach((btn) => btn.setAttribute("aria-expanded", "false"));
  });

  // Debug: confirm form submit
  document.addEventListener(
    "submit",
    (e) => {
      if (e.target.matches("[data-rate-form], .rate-form")) {
        console.log("✅ rate form submitted:", e.target.action);
      }
    },
    true
  );
}

/* =========================
   Boot
========================= */
document.addEventListener("DOMContentLoaded", () => {
  initMobileMenu();
  initRatings();
  updateDates();
  updateCountdowns();

  // كل دقيقة نحدّث (مزيان و خفيف)
  setInterval(() => {
    updateDates();
    updateCountdowns();
  }, 60 * 1000);
});

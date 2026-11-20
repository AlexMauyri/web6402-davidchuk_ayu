const targets = Array.from(document.querySelectorAll([
    "main h1", "main h2", "main h3", "main p",
    "main .image-wrapper", "main .logo-hero-wrapper",
    "main .timeline__item", "footer > .container",
].join(", ")));
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

if (targets.length && !reducedMotion.matches && "IntersectionObserver" in window) {
    let observer;
    const pending = new Set();

    function showAll() {
        observer?.disconnect();
        pending.clear();
        targets.forEach((target) => {
            target.classList.remove("scroll-reveal--pending", "scroll-reveal--appearing");
            target.style.removeProperty("--reveal-delay");
        });
    }

    function reveal(target, delay = 0) {
        if (!pending.delete(target)) return;
        observer.unobserve(target);
        target.style.setProperty("--reveal-delay", `${delay}ms`);
        target.classList.remove("scroll-reveal--pending");
        target.classList.add("scroll-reveal--appearing");
    }

    try {
        observer = new IntersectionObserver((entries) => {
            if (reducedMotion.matches) {
                showAll();
                return;
            }
            const entering = new Set(entries
                .filter((entry) => entry.isIntersecting && pending.has(entry.target))
                .map((entry) => entry.target));
            targets.filter((target) => entering.has(target)).forEach((target, index) => {
                reveal(target, Math.min(index, 2) * 140);
            });
        }, { threshold: 0, rootMargin: `0px 0px -${Math.min(80, Math.round(window.innerHeight * 0.1))}px 0px` });

        // Не анимируем одновременно родителя и вложенный в него текст.
        targets.forEach((target) => {
            if (targets.some((parent) => parent !== target && parent.contains(target))) return;
            pending.add(target);
            target.classList.add("scroll-reveal--pending");
            observer.observe(target);
        });
        reducedMotion.addEventListener("change", (event) => {
            if (event.matches) showAll();
        });
        window.addEventListener("pageshow", (event) => {
            if (event.persisted) showAll();
        });
        window.addEventListener("beforeprint", showAll);
        document.addEventListener("focusin", (event) => {
            const target = event.target.closest(".scroll-reveal--pending");
            if (target) reveal(target);
        });
    } catch {
        showAll();
    }
}

const cards = Array.from(document.querySelectorAll(".timeline__item"));
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

if (cards.length && !reducedMotion.matches && "IntersectionObserver" in window) {
    const shown = new WeakSet();
    const observer = new IntersectionObserver((entries) => {
        if (reducedMotion.matches) return;
        const entering = new Set(entries
            .filter((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.35 && !shown.has(entry.target))
            .map((entry) => entry.target));

        cards.filter((card) => entering.has(card)).forEach((card, index) => {
            shown.add(card);
            observer.unobserve(card);
            card.style.setProperty("--timeline-delay", `${Math.min(index, 2) * 180}ms`);
            card.classList.add("timeline__item--appearing");
        });
    }, { threshold: 0.35, rootMargin: "0px 0px -80px 0px" });

    cards.forEach((card) => observer.observe(card));
    reducedMotion.addEventListener("change", (event) => {
        if (!event.matches) return;
        observer.disconnect();
        cards.forEach((card) => {
            card.classList.remove("timeline__item--appearing");
            card.style.removeProperty("--timeline-delay");
        });
    });
}

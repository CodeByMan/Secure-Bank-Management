// Header JS: mobile menu toggle and profile dropdown behavior
(function () {
    window.toggleMobileMenu = function() {
        const mobileNav = document.querySelector('.mobile-nav');
        const overlay = document.querySelector('.mobile-overlay');
        const toggle = document.querySelector('.mobile-menu-toggle');
        const body = document.body;
        if (!mobileNav || !overlay || !toggle) return;
        mobileNav.classList.toggle('active');
        overlay.classList.toggle('active');
        toggle.classList.toggle('active');
        body.classList.toggle('menu-open');
    };

    // Profile dropdown toggle (desktop)
    document.addEventListener('DOMContentLoaded', function () {
        const profileToggle = document.getElementById('profileToggle');
        const profileMenu = document.querySelector('.profile-dropdown .dropdown-menu');
        if (!profileToggle) return;
        profileToggle.addEventListener('click', function(e) {
            const expanded = this.getAttribute('aria-expanded') === 'true';
            this.setAttribute('aria-expanded', String(!expanded));
            profileMenu.classList.toggle('show');
        });
        // Close when clicking outside
        document.addEventListener('click', function(e) {
            if (!profileToggle.contains(e.target) && profileMenu && !profileMenu.contains(e.target)) {
                profileMenu.classList.remove('show');
                profileToggle.setAttribute('aria-expanded', 'false');
            }
        });
    });
})();

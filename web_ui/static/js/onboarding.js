(function () {
  const STORAGE_KEY = 'veracli_onboarding_pref';

  function shouldRunTour() {
    return localStorage.getItem(STORAGE_KEY) !== 'skip';
  }

  function startTour() {
    const intro = introJs();

    intro.setOptions({
      steps: [
        {
          element: '#region-select',
          intro: 'Choose the platform region you want to work with.'
        },
        {
          element: '#env-select',
          intro: 'Select or authorize an environment before running commands.'
        },
        {
          element: '#command-sidebar',
          intro: 'All Veracli actions are grouped here by functionality.'
        },
        {
          element: '#use-default-checkbox',
          intro: 'Uncheck this to enable environments and sidebar.'
        },
        {
          element: '#cli-container',
          intro: 'This is the live Veracli shell output.'
        },
        {
          element: '#cli-input',
          intro: 'You can also type any Veracli command directly here.'
        },
        {
          element: '#clear-all-btn',
          intro: 'Clear the CLI output area with this button.'
        },
        {
          element: '#help-btn',
          intro: 'You can relaunch this walkthrough anytime from Help.'
        }
      ],
      showProgress: true,
      showBullets: false,
      exitOnOverlayClick: false,
      nextLabel: 'Next',
      prevLabel: 'Back',
      skipLabel: 'Skip',
      doneLabel: 'Finish'
    });

    intro.oncomplete(showPreferencePrompt);
    intro.onexit(showPreferencePrompt);

    intro.start();
  }

  function showPreferencePrompt() {
    const modal = document.getElementById('tour-pref-modal');
    modal.classList.remove('hidden');

    document.getElementById('tour-yes').onclick = () => {
        localStorage.setItem(STORAGE_KEY, 'show');
        modal.classList.add('hidden');
    };

    document.getElementById('tour-no').onclick = () => {
        localStorage.setItem(STORAGE_KEY, 'skip');
        modal.classList.add('hidden');
    };
  }

  // Auto-run on first load
  document.addEventListener('DOMContentLoaded', () => {
    if (shouldRunTour()) {
      setTimeout(startTour, 600); // wait for layout & socket init
    }
  });

  // Expose manual trigger (used by Help button)
  window.startVeracliTour = startTour;
})();

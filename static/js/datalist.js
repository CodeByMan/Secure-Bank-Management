document.addEventListener('alpine:init', () => {
    Alpine.data('customDatalist', (config) => ({
        options: config.options || [],
        optionValue: config.optionValue || 'id',
        optionLabel: config.optionLabel || 'name',
        selectedValue: config.selected || '',
        searchQuery: '',
        isOpen: false,
        highlightedIndex: -1,
        filteredOptions: [],
        searchable: config.searchable !== false,
        
        getOptionValue(option) {
            return option[this.optionValue];
        },
        
        getOptionLabel(option) {
            return option[this.optionLabel];
        },
        
        init() {
            this.filteredOptions = this.options;
            
            // Set initial search query to selected label
            if (this.selectedValue) {
                const selectedOption = this.options.find(opt => String(opt[this.optionValue]) === String(this.selectedValue));
                if (selectedOption) {
                    this.searchQuery = this.getOptionLabel(selectedOption);
                }
            }

            this.$nextTick(() => {
                try {
                    // Set input title if there's an initial selected label (so long selected labels are readable on hover)
                    const inputEl = this.$el.querySelector('.datalist-input');
                    if (inputEl && this.searchQuery) {
                        inputEl.title = this.searchQuery;
                    }
                } catch (err) {
                    // Ignore not-critical errors
                }
            });
        },
        
        toggle() {
            if (this.isOpen) {
                this.close();
            } else {
                this.open();
            }
        },
        
        open() {
            this.isOpen = true;
            this.highlightedIndex = -1;
            if (this.searchable) {
                this.$nextTick(() => {
                    const input = this.$el.querySelector('.datalist-input');
                    if (input) input.focus();
                });
            }
        },
        
        close() {
            this.isOpen = false;
            // Restore selected value label if search was cleared or no new selection made
            if (this.selectedValue) {
                const selectedOption = this.options.find(opt => String(opt[this.optionValue]) === String(this.selectedValue));
                if (selectedOption) {
                    this.searchQuery = this.getOptionLabel(selectedOption);
                }
            } else {
                this.searchQuery = '';
            }
        },

        
        handleSearch() {
            if (!this.searchable) return;
            
            this.isOpen = true;
            const query = this.searchQuery.toLowerCase();
            this.selectedValue = ''; // Clear selection when typing
            
            // Update input title so user can hover to see full typed value
            const inputEl = this.$el.querySelector('.datalist-input');
            if (inputEl) inputEl.title = this.searchQuery || '';

            if (!query) {
                this.filteredOptions = this.options;
            } else {
                this.filteredOptions = this.options.filter(option => {
                    const label = String(this.getOptionLabel(option)).toLowerCase();
                    return label.includes(query);
                });
            }
            
            this.highlightedIndex = -1;
        }, 
        
        select(option) {
            this.selectedValue = this.getOptionValue(option);
            this.searchQuery = this.getOptionLabel(option);
            // Ensure input title is updated so long selected labels are visible on hover
            const inputEl = this.$el.querySelector('.datalist-input');
            if (inputEl) inputEl.title = this.searchQuery || '';

            this.isOpen = false;
            this.filteredOptions = this.options;
            
            // Dispatch native change event for the hidden input (for form submission)
            this.$nextTick(() => {
                // Prefer ref, then local hidden input, then global lookup by name
                const hiddenInput = this.$refs.hidden || this.$el.querySelector('input[type="hidden"]') || document.querySelector(`input[name="${this.name}"][type="hidden"]`);
                if (hiddenInput) {
                    hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
                
                // Dispatch Custom Event on root element to match user snippet
                this.$el.dispatchEvent(new CustomEvent('change', {
                    detail: { value: this.selectedValue, option: option },
                    bubbles: true
                }));
            });
        },
        
        clear() {
            this.selectedValue = '';
            this.searchQuery = '';
            this.filteredOptions = this.options;
            this.isOpen = false;
             this.$nextTick(() => {
                const hiddenInput = this.$refs.hidden || this.$el.querySelector('input[type="hidden"]') || document.querySelector(`input[name="${this.name}"][type="hidden"]`);
                if (hiddenInput) {
                    hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
                
                 // Dispatch Custom Event on root element
                this.$el.dispatchEvent(new CustomEvent('change', {
                    detail: { value: '', option: null },
                    bubbles: true
                }));
            });
        },
        
        selectFirst() {
            if (this.isOpen && this.filteredOptions.length > 0) {
                if (this.highlightedIndex >= 0 && this.highlightedIndex < this.filteredOptions.length) {
                    this.select(this.filteredOptions[this.highlightedIndex]);
                } else {
                    this.select(this.filteredOptions[0]);
                }
            }
        },
        
        navigateDown() {
            if (!this.isOpen) {
                this.open();
                return;
            }
            
            if (this.highlightedIndex < this.filteredOptions.length - 1) {
                this.highlightedIndex++;
                this.scrollToHighlighted();
            }
        },
        
        navigateUp() {
            if (this.highlightedIndex > 0) {
                this.highlightedIndex--;
                this.scrollToHighlighted();
            }
        },
        
        scrollToHighlighted() {
            this.$nextTick(() => {
                const optionsList = this.$refs.optionsList;
                if (!optionsList) return;
                const highlightedOption = optionsList.children[this.highlightedIndex];
                
                if (highlightedOption) {
                    highlightedOption.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            });
        }
    }));
});
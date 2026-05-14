from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, OptionList
from textual import on, events
from textual.message import Message

class SearchableSelect(Vertical):
    """A custom filterable combobox widget."""
    
    class Changed(Message):
        def __init__(self, value: str, select: "SearchableSelect"):
            self.value = value
            self.select = select
            super().__init__()
            
        @property
        def control(self):
            return self.select
            
    def __init__(self, prompt: str = "Search...", id: str = None):
        super().__init__(id=id)
        self.prompt = prompt
        self._options = []
        self._current_value = ""
        self._selecting = False

    def compose(self) -> ComposeResult:
        yield Input(placeholder=self.prompt, id="search_input")
        yield OptionList(id="search_options", classes="hidden")
        
    def set_options(self, options: list[tuple[str, str] | str]):
        self._options = []
        for opt in options:
            if isinstance(opt, tuple):
                self._options.append((str(opt[0]), str(opt[1])))
            else:
                self._options.append((str(opt), str(opt)))
        
        self._repopulate_options()
            
    def _repopulate_options(self, filter_term: str = ""):
        opt_list = self.query_one("#search_options", OptionList)
        opt_list.clear_options()
        
        has_matches = False
        for label, val in self._options:
            if not filter_term or filter_term in label.lower() or filter_term in val.lower():
                opt_list.add_option(label)
                has_matches = True
                
        return has_matches
            
    @property
    def value(self) -> str:
        return self._current_value
        
    @value.setter
    def value(self, new_value: str):
        self._current_value = new_value
        label = new_value
        for l, v in self._options:
            if v == new_value:
                label = l
                break
                
        inp = self.query_one("#search_input", Input)
        with inp.prevent(Input.Changed):
            inp.value = label
            
        self.post_message(self.Changed(new_value, self))
        
    @on(Input.Changed, "#search_input")
    def on_input_changed(self, event: Input.Changed):
        if self._selecting:
            self._selecting = False
            return
            
        opt_list = self.query_one("#search_options", OptionList)
        search_term = event.value.lower()
        
        has_matches = self._repopulate_options(search_term)
                
        if has_matches:
            opt_list.remove_class("hidden")
            opt_list.add_class("visible")
        else:
            opt_list.remove_class("visible")
            opt_list.add_class("hidden")
            
        if not event.value:
            self._current_value = ""
            self.post_message(self.Changed("", self))

    @on(events.Click, "#search_input")
    def on_input_clicked(self, event: events.Click):
        opt_list = self.query_one("#search_options", OptionList)
        inp = self.query_one("#search_input", Input)
        has_matches = self._repopulate_options(inp.value.lower())
        if has_matches:
            opt_list.remove_class("hidden")
            opt_list.add_class("visible")

    @on(Input.Submitted, "#search_input")
    def on_input_submitted(self, event: Input.Submitted):
        # If they press enter, maybe focus the list or select first
        pass
            
    @on(OptionList.OptionSelected, "#search_options")
    def on_option_selected(self, event: OptionList.OptionSelected):
        label = str(event.option.prompt)
        val = label
        for l, v in self._options:
            if l == label:
                val = v
                break
                
        self._current_value = val
        self._selecting = True
        
        inp = self.query_one("#search_input", Input)
        inp.value = label
            
        opt_list = self.query_one("#search_options", OptionList)
        opt_list.remove_class("visible")
        opt_list.add_class("hidden")
        
        self.post_message(self.Changed(val, self))

    def focus_input(self):
        self.query_one("#search_input", Input).focus()

import asyncio
from src.main import LlamaCockpitApp

async def test():
    app = LlamaCockpitApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        
        print("Initial configs count:", len(app.current_configs))
        print("Config names:", [c["name"] for c in app.current_configs])
        
        sel = app.query_one("#sel_creator_config")
        print("SearchableSelect options:", sel._options)
        
        # Set the value to 'Thinking (Coding)'
        sel.value = "Thinking (Coding)"
        
        await pilot.pause()
        
        inp_name = app.query_one("#inp_config_name").value
        inp_commands = app.query_one("#inp_config_commands").value
        inp_models = app.query_one("#inp_config_models").value
        
        print(f"Loaded config values:\nName: {inp_name!r}\nCommands: {inp_commands!r}\nModels: {inp_models!r}")
        
        assert inp_name == "Thinking (Coding)", f"Expected 'Thinking (Coding)', got {inp_name!r}"
        assert "--temp 0.6" in inp_commands, f"Expected commands to contain temperature setting, got {inp_commands!r}"
        print("Success! Config loaded correctly.")

if __name__ == "__main__":
    asyncio.run(test())

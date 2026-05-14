# Llama Cockpit

A modern Terminal User Interface (TUI) for managing Llama.cpp toolboxes and models on AMD Strix Halo hardware.

## Installation

The easiest way to install Llama Cockpit is via `pipx`, which manages isolated environments for Python CLI tools:

```bash
# If you don't have pipx installed:
# Ubuntu/Debian: sudo apt install pipx
# Fedora: sudo dnf install pipx
# Arch: sudo pacman -S python-pipx

pipx install git+https://github.com/kyuz0/llama-toolboxes-cockpit.git
```

## Usage

Launch the TUI from your terminal:

```bash
llama-cockpit
```

## Features

- **Interactive Toolboxes**: Easily enter, update, or remove Llama.cpp CLI toolboxes via distrobox/toolbox.
- **Server Mode**: Launch a Llama.cpp inference server directly from a container in the background, without entering the interactive shell.
- **Model Manager**: Scan your `~/models` directory and download curated GGUF models from Hugging Face.

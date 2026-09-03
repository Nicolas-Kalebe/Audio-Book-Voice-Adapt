from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, Tk, filedialog, messagebox
from tkinter import scrolledtext, ttk
from typing import Any

import yaml

from .character_discovery import merge_detected_characters
from .audio import SUPPORTED, natural_key, probe
from .config import ConfigurationError, load_characters, load_config
from .planning import analysis_for_selection, clock, estimate_job

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"
CHARACTERS_PATH = ROOT / "config" / "characters.json"

BG = "#04070d"
PANEL = "#09111f"
PANEL_2 = "#0d1b2d"
NAVY = "#102a46"
ACCENT = "#1683ff"
ACCENT_HOVER = "#0868d7"
TEXT = "#e8f1ff"
MUTED = "#91a4bd"
SUCCESS = "#39d98a"
DANGER = "#ff5b69"
BORDER = "#173552"
PROGRESS_PATTERN = re.compile(r"\[PROGRESS\]\s+([\d.]+)%")
CHAPTER_PATTERN = re.compile(r"capítulo\s+(\d+)/(\d+)\s+\|\s+(.+?)\s+\|\s+(.+?)(?:\r?\n)?$")


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def atomic_yaml(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    temporary.replace(path)


def relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def resolve_voice_reference(root: Path, character: dict[str, Any]) -> Path | None:
    value = character.get("voice_reference")
    if not value:
        return None
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def character_speech_stats(report: dict[str, Any]) -> dict[str, tuple[int, float]]:
    detected = report.get("characters_detected", {})
    counts = {str(name): int(count) for name, count in detected.items()
              if str(name).casefold() not in {"unknown", "desconhecido"} and int(count) > 0}
    total = sum(counts.values())
    return {name.casefold(): (count, count / total if total else 0.0) for name, count in counts.items()}


class App(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Audio-Book Voice Adapt")
        self.geometry("1180x780")
        self.minsize(1020, 680)
        self.configure(bg=BG)
        self.option_add("*Font", ("Segoe UI", 10))
        self.process: subprocess.Popen[str] | None = None
        self.task_kind = "idle"
        self.last_command = ""
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.config_data = load_config(CONFIG_PATH)
        self.startup_import = self._sync_detected_characters(ROOT / "output" / "analysis.json")
        self.characters = self._read_characters()
        self._style()
        self._header()
        self._tabs()
        if self.startup_import["added"]:
            self._log(f"{len(self.startup_import['added'])} personagem(ns) da última análise foram adicionados automaticamente.\n")
        self.after(100, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 21))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(20, 11), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", NAVY)], foreground=[("selected", TEXT)])
        style.configure("TEntry", fieldbackground=PANEL_2, foreground=TEXT, bordercolor=BORDER, insertcolor=TEXT, padding=7)
        style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, arrowcolor=TEXT, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", TEXT)])
        style.configure("Treeview", background=PANEL_2, fieldbackground=PANEL_2, foreground=TEXT,
                        rowheight=30, bordercolor=BORDER)
        style.configure("Treeview.Heading", background=NAVY, foreground=TEXT, relief="flat", padding=6)
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", PANEL)])

    def _header(self) -> None:
        header = ttk.Frame(self, padding=(24, 18, 24, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Audio-Book Voice Adapt", style="Title.TLabel").pack(side="left")
        self.status = ttk.Label(header, text="● Pronto", foreground=SUCCESS)
        self.status.pack(side="right")

    def _tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=22, pady=(0, 20))
        self.process_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=22)
        self.characters_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=22)
        self.settings_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=22)
        self.preview_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=22)
        self.notebook.add(self.process_tab, text="PROCESSAMENTO")
        self.notebook.add(self.characters_tab, text="PERSONAGENS E VOZES")
        self.notebook.add(self.settings_tab, text="CONFIGURAÇÕES")
        self.notebook.add(self.preview_tab, text="PRÉVIA A/B")
        self._process_ui()
        self._characters_ui()
        self._settings_ui()
        self._preview_ui()

    def _process_ui(self) -> None:
        tab = self.process_tab
        tab.columnconfigure(1, weight=1)
        default_book = ROOT / "books" / "O Sangue dos Elfos.epub"
        self.source_var = StringVar(value=str(ROOT / "input"))
        self.book_var = StringVar(value=str(default_book) if default_book.is_file() else "")
        self.output_var = StringVar(value=str(ROOT / "output"))
        self.run_language = StringVar(value=str(self.config_data.get("language", "auto")))
        self.run_model = StringVar(value=str(self.config_data.get("transcription", {}).get("model", "large-v3")))
        self.audio_selection: dict[str, bool] = {}
        self.audio_durations: dict[str, float] = {}

        self._section(tab, "Arquivos", "Selecione a pasta que contém todos os MP3s. Cada capítulo terá uma saída separada.", 0)
        self._path_row(tab, "Capítulos", self.source_var, self._choose_source, 2)
        self._path_row(tab, "Livro", self.book_var, self._choose_book, 3)
        self._path_row(tab, "Saída", self.output_var, self._choose_output, 4)

        chapter_box = ttk.Frame(tab, style="Panel.TFrame")
        chapter_box.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Label(chapter_box, text="Capítulos — clique duas vezes para incluir/excluir", style="Panel.TLabel").pack(side="left")
        self._button(chapter_box, "Todos", lambda: self._set_all_chapters(True)).pack(side="right")
        self._button(chapter_box, "Nenhum", lambda: self._set_all_chapters(False)).pack(side="right", padx=7)
        self.chapter_tree = ttk.Treeview(tab, columns=("include", "duration", "status"), show="tree headings", height=5)
        self.chapter_tree.heading("#0", text="Arquivo")
        for column, title, width in (("include", "Incluir", 70), ("duration", "Duração", 90), ("status", "Estado", 220)):
            self.chapter_tree.heading(column, text=title)
            self.chapter_tree.column(column, width=width, anchor="w")
        self.chapter_tree.column("#0", width=390)
        self.chapter_tree.grid(row=6, column=0, columnspan=3, sticky="ew")
        self.chapter_tree.bind("<Double-1>", self._toggle_chapter)

        ttk.Label(tab, text="Idioma", style="Panel.TLabel").grid(row=7, column=0, sticky="w", pady=(10, 3))
        ttk.Combobox(tab, textvariable=self.run_language, values=("auto", "pt", "en", "es", "fr", "de"), width=12).grid(row=8, column=0, sticky="w")
        ttk.Label(tab, text="Modelo Whisper", style="Panel.TLabel").grid(row=7, column=1, sticky="w", padx=(14, 0), pady=(10, 3))
        ttk.Combobox(tab, textvariable=self.run_model, values=("tiny", "small", "medium", "distil-large-v3", "large-v3"), width=22).grid(row=8, column=1, sticky="w", padx=(14, 0))

        actions = ttk.Frame(tab, style="Panel.TFrame")
        actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        self.run_buttons = [
            self._button(actions, "Analisar", lambda: self._start("analyze", False)),
            self._button(actions, "Dry run", lambda: self._start("process", True)),
            self._button(actions, "Processar capítulos", lambda: self._start("process", False), accent=True),
            self._button(actions, "Cancelar", self._cancel, danger=True),
        ]
        for index, button in enumerate(self.run_buttons):
            button.pack(side="left", padx=(0, 9))
        self._button(actions, "Estimativa", self._show_estimate).pack(side="left")
        self._button(actions, "Abrir saída", lambda: self._open_path(Path(self.output_var.get()))).pack(side="right")
        self._button(actions, "Abrir relatório", self._open_report).pack(side="right", padx=(0, 9))

        self.progress = ttk.Progressbar(tab, mode="determinate", maximum=100)
        self.progress.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        self.progress_detail = StringVar(value="Aguardando")
        ttk.Label(tab, textvariable=self.progress_detail, style="Muted.TLabel").grid(row=11, column=0, columnspan=3, sticky="w", pady=(0, 7))
        self.log = scrolledtext.ScrolledText(tab, height=8, bg="#02050a", fg="#b9d7ff", insertbackground=TEXT,
                                             relief="flat", borderwidth=0, font=("Cascadia Mono", 9), padx=10, pady=10)
        self.log.grid(row=12, column=0, columnspan=3, sticky="nsew")
        tab.rowconfigure(12, weight=1)
        self._refresh_chapters()
        self._log("Interface pronta. Coloque os MP3s em input/ e configure as vozes antes de processar.\n")

    def _characters_ui(self) -> None:
        tab = self.characters_tab
        tab.columnconfigure(0, weight=3)
        tab.columnconfigure(1, weight=2)
        tab.rowconfigure(2, weight=1)
        self._section(tab, "Personagens", "Ordenados pelo número de falas; peso = participação entre as falas com personagem identificado.", 0, span=2)
        columns = ("speeches", "weight", "mode", "gender", "age", "voice", "status")
        self.character_tree = ttk.Treeview(tab, columns=columns, show="tree headings", selectmode="browse")
        self.character_tree.heading("#0", text="Nome")
        for column, title, width in (("speeches", "Falas", 58), ("weight", "Peso", 65), ("mode", "Modo", 75),
                                     ("gender", "Gênero", 70), ("age", "Idade", 65),
                                     ("voice", "Referência", 130), ("status", "Estado", 90)):
            self.character_tree.heading(column, text=title)
            self.character_tree.column(column, width=width, anchor="w")
        self.character_tree.column("#0", width=135)
        self.character_tree.grid(row=2, column=0, sticky="nsew", padx=(0, 16), pady=(12, 0))
        self.character_tree.bind("<<TreeviewSelect>>", self._select_character)

        editor = ttk.Frame(tab, style="Panel.TFrame")
        editor.grid(row=2, column=1, sticky="nsew", pady=(12, 0))
        self.char_name = StringVar()
        self.char_aliases = StringVar()
        self.char_mode = StringVar(value="original")
        self.char_gender = StringVar()
        self.char_age = StringVar()
        self.char_voice = StringVar()
        self.char_pitch = DoubleVar(value=0)
        ttk.Label(editor, text="Nome", style="Panel.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))
        ttk.Entry(editor, textvariable=self.char_name).grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(editor, text="Aliases, separados por vírgula", style="Panel.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 3))
        ttk.Entry(editor, textvariable=self.char_aliases).grid(row=3, column=0, columnspan=2, sticky="ew")
        paired = (("Modo", self.char_mode, ("original", "convert", "auto", "ignore")),
                  ("Gênero", self.char_gender, ("", "female", "male", "nonbinary", "other")),
                  ("Faixa etária", self.char_age, ("", "child", "teen", "adult", "elder")),
                  ("Pitch", self.char_pitch, None))
        for index, (label, variable, values) in enumerate(paired):
            column, pair_row = index % 2, 4 + (index // 2) * 2
            ttk.Label(editor, text=label, style="Panel.TLabel").grid(row=pair_row, column=column, sticky="w",
                                                                      padx=(0, 5) if column == 0 else (5, 0), pady=(8, 3))
            widget = ttk.Combobox(editor, textvariable=variable, values=values, state="readonly") if values else ttk.Entry(editor, textvariable=variable)
            widget.grid(row=pair_row + 1, column=column, sticky="ew", padx=(0, 5) if column == 0 else (5, 0))
        ttk.Label(editor, text="Referência de voz", style="Panel.TLabel").grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 3))
        ttk.Entry(editor, textvariable=self.char_voice).grid(row=9, column=0, columnspan=2, sticky="ew")
        voice_actions = ttk.Frame(editor, style="Panel.TFrame")
        voice_actions.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 6))
        self._button(voice_actions, "Importar voz", self._import_voice, accent=True).pack(side="left", fill="x", expand=True)
        self._button(voice_actions, "Ouvir", self._play_reference).pack(side="left", padx=(7, 0))
        self._button(editor, "Salvar", self._save_character).grid(row=11, column=0, sticky="ew", padx=(0, 5), pady=4)
        self._button(editor, "Atualizar da análise", self._import_characters_from_analysis).grid(row=11, column=1, sticky="ew", padx=(5, 0), pady=4)
        self._button(editor, "Novo", self._clear_character).grid(row=12, column=0, sticky="ew", padx=(0, 5), pady=4)
        self._button(editor, "Excluir", self._delete_character, danger=True).grid(row=12, column=1, sticky="ew", padx=(5, 0), pady=4)
        editor.columnconfigure(0, weight=1)
        editor.columnconfigure(1, weight=1)
        self._refresh_characters()

    def _settings_ui(self) -> None:
        tab = self.settings_tab
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        self._section(tab, "Configurações principais", "Os valores são salvos em config/config.yaml.", 0, span=2)
        transcription = self.config_data.get("transcription", {})
        output = self.config_data.get("output", {})
        vc = self.config_data.get("voice_conversion", {})
        llm = self.config_data.get("llm", {})
        self.setting_vars: dict[str, Any] = {
            "device": StringVar(value=self.config_data.get("device", "auto")),
            "model": StringVar(value=transcription.get("model", "large-v3")),
            "compute": StringVar(value=transcription.get("compute_type", "float16")),
            "speaker": DoubleVar(value=self.config_data.get("speaker_confidence_threshold", .85)),
            "alignment": DoubleVar(value=self.config_data.get("alignment_confidence_threshold", .8)),
            "duration": DoubleVar(value=self.config_data.get("minimum_segment_duration", .8)),
            "padding": IntVar(value=self.config_data.get("padding_ms", 150)),
            "backend": StringVar(value=vc.get("backend", "auto")),
            "format": StringVar(value=output.get("format", "mp3")),
            "bitrate": StringVar(value=output.get("bitrate", "320k")),
            "llm_enabled": BooleanVar(value=llm.get("enabled", True)),
            "llm_provider": StringVar(value=llm.get("provider", "ollama")),
            "llm_url": StringVar(value=llm.get("base_url", "http://localhost:11434")),
            "llm_model": StringVar(value=llm.get("model", "")),
        }
        left = ttk.Frame(tab, style="Panel.TFrame")
        right = ttk.Frame(tab, style="Panel.TFrame")
        left.grid(row=2, column=0, sticky="new", padx=(0, 18), pady=(16, 0))
        right.grid(row=2, column=1, sticky="new", pady=(16, 0))
        self._settings_fields(left, (("Dispositivo", "device", ("auto", "cuda", "cpu")),
                                    ("Modelo Whisper", "model", ("tiny", "small", "medium", "distil-large-v3", "large-v3")),
                                    ("Precisão", "compute", ("float16", "int8_float16", "int8")),
                                    ("Confiança do falante", "speaker", None), ("Confiança do alinhamento", "alignment", None),
                                    ("Duração mínima (s)", "duration", None), ("Padding (ms)", "padding", None)))
        self._settings_fields(right, (("Backend de voz", "backend", ("auto", "seedvc", "openvoice", "rvc")),
                                     ("Formato de saída", "format", ("mp3", "m4a", "flac", "wav", "opus", "ogg")),
                                     ("Bitrate", "bitrate", ("128k", "192k", "256k", "320k")),
                                     ("Provedor LLM", "llm_provider", ("ollama", "openai-compatible")),
                                     ("URL do LLM", "llm_url", None), ("Modelo LLM (vazio desativa chamadas)", "llm_model", None)))
        ttk.Checkbutton(right, text="LLM habilitado", variable=self.setting_vars["llm_enabled"]).pack(anchor="w", pady=(12, 4))
        button_row = ttk.Frame(tab, style="Panel.TFrame")
        button_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(24, 0))
        self._button(button_row, "Salvar configurações", self._save_settings, accent=True).pack(side="left")
        self._button(button_row, "Verificar GPU", self._check_gpu).pack(side="left", padx=9)

    def _preview_ui(self) -> None:
        tab = self.preview_tab
        tab.columnconfigure(1, weight=1)
        self._section(tab, "Prévia e comparação A/B",
                      "Converta somente 3–60 segundos antes de processar o capítulo inteiro.", 0)
        self.preview_audio = StringVar()
        self.preview_character = StringVar()
        self.preview_start = StringVar(value="0")
        self.preview_duration = IntVar(value=20)
        ttk.Label(tab, text="Capítulo", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=7)
        self.preview_audio_box = ttk.Combobox(tab, textvariable=self.preview_audio, state="readonly")
        self.preview_audio_box.grid(row=2, column=1, columnspan=2, sticky="ew", pady=7)
        ttk.Label(tab, text="Personagem", style="Panel.TLabel").grid(row=3, column=0, sticky="w", pady=7)
        self.preview_character_box = ttk.Combobox(tab, textvariable=self.preview_character, state="readonly")
        self.preview_character_box.grid(row=3, column=1, columnspan=2, sticky="ew", pady=7)
        ttk.Label(tab, text="Início em segundos", style="Panel.TLabel").grid(row=4, column=0, sticky="w", pady=7)
        ttk.Entry(tab, textvariable=self.preview_start).grid(row=4, column=1, sticky="ew", pady=7)
        ttk.Label(tab, text="Duração (3–60 s)", style="Panel.TLabel").grid(row=5, column=0, sticky="w", pady=7)
        ttk.Entry(tab, textvariable=self.preview_duration).grid(row=5, column=1, sticky="ew", pady=7)
        actions = ttk.Frame(tab, style="Panel.TFrame")
        actions.grid(row=6, column=0, columnspan=3, sticky="w", pady=(18, 10))
        self._button(actions, "Localizar fala", self._locate_preview_dialogue).pack(side="left")
        self._button(actions, "Gerar prévia", self._generate_preview, accent=True).pack(side="left", padx=(8, 0))
        self.preview_original_button = self._button(actions, "Ouvir original", lambda: self._play_preview("original"))
        self.preview_original_button.pack(side="left", padx=8)
        self.preview_converted_button = self._button(actions, "Ouvir convertido", lambda: self._play_preview("converted"))
        self.preview_converted_button.pack(side="left")
        self.preview_original_button.configure(state="disabled")
        self.preview_converted_button.configure(state="disabled")
        ttk.Label(tab, text="Dica: escolha um ponto com fala clara do narrador. As duas amostras terão exatamente a mesma duração.",
                  style="Muted.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(5, 0))
        self.preview_paths: dict[str, Path] = {}
        self._refresh_preview_options()

    def _settings_fields(self, parent: ttk.Frame, fields: tuple[tuple[str, str, tuple[str, ...] | None], ...]) -> None:
        for label, key, values in fields:
            ttk.Label(parent, text=label, style="Panel.TLabel").pack(anchor="w", pady=(8, 3))
            if values:
                ttk.Combobox(parent, textvariable=self.setting_vars[key], values=values, state="readonly").pack(fill="x")
            else:
                ttk.Entry(parent, textvariable=self.setting_vars[key]).pack(fill="x")

    def _section(self, parent: ttk.Frame, title: str, subtitle: str, row: int, span: int = 3) -> None:
        ttk.Label(parent, text=title, style="Panel.TLabel", font=("Segoe UI Semibold", 16)).grid(row=row, column=0, columnspan=span, sticky="w")
        ttk.Label(parent, text=subtitle, style="Muted.TLabel").grid(row=row + 1, column=0, columnspan=span, sticky="w", pady=(3, 8))

    def _path_row(self, parent: ttk.Frame, label: str, variable: StringVar, command: Any, row: int) -> None:
        ttk.Label(parent, text=label, style="Panel.TLabel", width=12).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(0, 9), pady=5)
        self._button(parent, "Escolher", command).grid(row=row, column=2, pady=5)

    def _button(self, parent: Any, text: str, command: Any, *, accent: bool = False, danger: bool = False) -> Any:
        import tkinter as tk
        color = DANGER if danger else ACCENT if accent else NAVY
        hover = "#d94351" if danger else ACCENT_HOVER if accent else "#173b60"
        button = tk.Button(parent, text=text, command=command, bg=color, fg="white", activebackground=hover,
                           activeforeground="white", relief="flat", borderwidth=0, padx=14, pady=8, cursor="hand2")
        return button

    def _refresh_chapters(self) -> None:
        previous = dict(self.audio_selection)
        self.audio_selection.clear()
        self.audio_durations.clear()
        self.chapter_paths_by_iid: dict[str, Path] = {}
        for item in self.chapter_tree.get_children():
            self.chapter_tree.delete(item)
        source = Path(self.source_var.get())
        if source.is_file() and source.suffix.casefold() in SUPPORTED:
            files = [source.resolve()]
        elif source.is_dir():
            files = sorted((path.resolve() for path in source.iterdir()
                            if path.is_file() and path.suffix.casefold() in SUPPORTED), key=natural_key)
        else:
            files = []
        for index, path in enumerate(files):
            key = str(path)
            selected = previous.get(key, not path.stem.casefold().startswith(("smoke", "test")))
            try:
                duration = probe(path).duration
                duration_text = clock(duration)
            except Exception:
                duration = 0.0
                duration_text = "—"
            self.audio_selection[key] = selected
            self.audio_durations[key] = duration
            iid = f"chapter-{index}"
            self.chapter_paths_by_iid[iid] = path
            self.chapter_tree.insert("", "end", iid=iid, text=path.name,
                                     values=("✓" if selected else "—", duration_text,
                                             "Aguardando" if selected else "Ignorado"))
        self._refresh_preview_options()

    def _toggle_chapter(self, event: Any) -> None:
        iid = self.chapter_tree.identify_row(event.y)
        path = self.chapter_paths_by_iid.get(iid)
        if not path:
            return
        key = str(path)
        self.audio_selection[key] = not self.audio_selection[key]
        values = list(self.chapter_tree.item(iid, "values"))
        values[0] = "✓" if self.audio_selection[key] else "—"
        values[2] = "Aguardando" if self.audio_selection[key] else "Ignorado"
        self.chapter_tree.item(iid, values=values)
        self._refresh_preview_options()

    def _set_all_chapters(self, selected: bool) -> None:
        for iid, path in self.chapter_paths_by_iid.items():
            self.audio_selection[str(path)] = selected
            values = list(self.chapter_tree.item(iid, "values"))
            values[0] = "✓" if selected else "—"
            values[2] = "Aguardando" if selected else "Ignorado"
            self.chapter_tree.item(iid, values=values)
        self._refresh_preview_options()

    def _selected_audio(self) -> list[Path]:
        return [Path(path) for path, selected in self.audio_selection.items() if selected]

    def _refresh_preview_options(self) -> None:
        if not hasattr(self, "preview_audio_box"):
            return
        files = [str(path) for path in self._selected_audio()]
        self.preview_audio_box.configure(values=files)
        if files and self.preview_audio.get() not in files:
            self.preview_audio.set(files[0])
        names = [name for name in self.characters if name != "__narrator__"]
        self.preview_character_box.configure(values=names)
        if names and self.preview_character.get() not in names:
            self.preview_character.set(names[0])

    def _show_estimate(self) -> None:
        selected = self._selected_audio()
        if not selected:
            messagebox.showwarning("Estimativa", "Selecione pelo menos um capítulo.")
            return
        total = sum(self.audio_durations.get(str(path), 0) for path in selected)
        analysis_path = Path(self.output_var.get()) / "analysis.json"
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.is_file() else None
        except (OSError, json.JSONDecodeError):
            analysis = None
        if analysis:
            convertible = {name for name, item in self.characters.items() if item.get("mode") in {"convert", "auto"}
                           and item.get("voice_reference")}
            analysis = analysis_for_selection(analysis, {path.name for path in selected}, convertible,
                                              float(self.config_data["speaker_confidence_threshold"]),
                                              float(self.config_data["alignment_confidence_threshold"]))
        estimate = estimate_job(total, str(self.config_data.get("output", {}).get("bitrate", "320k")), analysis)
        conversion = clock(estimate["conversion_seconds"])
        time_range = f"{clock(estimate['minimum_seconds'])} a {clock(estimate['maximum_seconds'])}"
        cache_note = "transcrição já analisada" if analysis else "inclui estimativa de transcrição"
        messagebox.showinfo("Estimativa do trabalho",
                            f"Capítulos: {len(selected)}\nÁudio total: {clock(total)}\n"
                            f"Falas previstas para conversão: {conversion}\n"
                            f"Saída aproximada: {estimate['output_mb']:.1f} MB\n"
                            f"Tempo estimado: {time_range}\n\nEstimativa aproximada ({cache_note}).")

    def _generate_preview(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning("Em execução", "Aguarde a tarefa atual terminar.")
            return
        source = Path(self.preview_audio.get())
        character = self.preview_character.get()
        if not source.is_file() or not character:
            messagebox.showerror("Prévia", "Escolha um capítulo e um personagem.")
            return
        reference = resolve_voice_reference(ROOT, self.characters.get(character, {}))
        if not reference or not reference.is_file():
            self.notebook.select(self.characters_tab)
            if self.character_tree.exists(character):
                self.character_tree.selection_set(character)
                self.character_tree.focus(character)
                self._select_character()
            messagebox.showerror(
                "Voz de referência ausente",
                f"Importe primeiro um arquivo de voz para {character} na aba PERSONAGENS E VOZES.\n\n"
                "O caminho configurado atualmente não existe."
            )
            return
        try:
            start = float(self.preview_start.get().replace(",", "."))
            duration = int(self.preview_duration.get())
            if start < 0 or not 3 <= duration <= 60:
                raise ValueError
        except ValueError:
            messagebox.showerror("Prévia", "Use início positivo e duração entre 3 e 60 segundos.")
            return
        slug = re.sub(r"[^a-z0-9]+", "_", character.casefold()).strip("_") or "character"
        output = ROOT / "output" / "previews"
        self.preview_paths = {}
        self.pending_preview_paths = {"original": output / f"{slug}-original.wav",
                                      "converted": output / f"{slug}-converted.wav"}
        self.preview_original_button.configure(state="disabled")
        self.preview_converted_button.configure(state="disabled")
        args = [sys.executable, "-u", str(ROOT / "main.py"), "preview", str(source), character,
                "--start", str(start), "--duration", str(duration), "--config", str(CONFIG_PATH),
                "--characters", str(CHARACTERS_PATH), "--output", str(output)]
        self.task_kind = "preview"
        self.status.configure(text="● Gerando prévia", foreground=ACCENT)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        threading.Thread(target=self._worker, args=(args,), daemon=True).start()

    def _locate_preview_dialogue(self) -> None:
        character = self.preview_character.get()
        report_path = Path(self.output_var.get()) / "analysis.json"
        if not character or not report_path.is_file():
            messagebox.showwarning("Localizar fala", "Faça a análise e escolha um personagem primeiro.")
            return
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            selected = {path.name for path in self._selected_audio()}
            candidates = [(item, dialogue) for item in report.get("files", [])
                          if Path(item.get("input", "")).name in selected
                          for dialogue in item.get("dialogues", []) if dialogue.get("speaker") == character]
            if not candidates:
                raise LookupError
            item, dialogue = max(candidates, key=lambda pair: float(pair[1].get("speaker_confidence", 0)))
            self.preview_audio.set(str(Path(item["input"])))
            start = max(0.0, float(dialogue.get("start", 0)) - 1)
            duration = min(20, max(3, round(float(dialogue.get("end", start + 3)) - start + 1)))
            self.preview_start.set(f"{start:.2f}")
            self.preview_duration.set(duration)
            messagebox.showinfo("Fala localizada", "O melhor trecho encontrado foi selecionado para a prévia.")
        except (OSError, ValueError, json.JSONDecodeError, LookupError):
            messagebox.showwarning("Localizar fala", "Nenhuma fala desse personagem foi encontrada nos capítulos selecionados.")

    def _play_preview(self, kind: str) -> None:
        path = self.preview_paths.get(kind)
        if not path or not path.is_file():
            messagebox.showwarning("Prévia", "Gere a prévia antes de ouvir.")
            return
        self._open_path(path)

    def _choose_source(self) -> None:
        value = filedialog.askdirectory(initialdir=self.source_var.get() or ROOT)
        if value:
            self.source_var.set(value)
            self._refresh_chapters()

    def _choose_book(self) -> None:
        value = filedialog.askopenfilename(initialdir=ROOT / "books", filetypes=(("Livros", "*.epub *.txt *.srt *.json"), ("Todos", "*.*")))
        if value: self.book_var.set(value)

    def _choose_output(self) -> None:
        value = filedialog.askdirectory(initialdir=self.output_var.get() or ROOT)
        if value: self.output_var.set(value)

    def _read_characters(self) -> dict[str, dict[str, Any]]:
        return json.loads(CHARACTERS_PATH.read_text(encoding="utf-8"))

    def _sync_detected_characters(self, report_path: Path) -> dict[str, list[str]]:
        if not report_path.is_file():
            return {"added": [], "updated": []}
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return merge_detected_characters(CHARACTERS_PATH, report,
                                             float(self.config_data["speaker_confidence_threshold"]))
        except (OSError, ValueError, json.JSONDecodeError):
            return {"added": [], "updated": []}

    def _import_characters_from_analysis(self) -> None:
        result = self._sync_detected_characters(Path(self.output_var.get()) / "analysis.json")
        self.characters = self._read_characters()
        self._refresh_characters()
        if result["added"]:
            messagebox.showinfo("Personagens importados", f"Adicionados: {', '.join(result['added'])}")
        else:
            messagebox.showinfo("Personagens", "Nenhum personagem novo foi encontrado no relatório.")

    def _refresh_characters(self) -> None:
        for item in self.character_tree.get_children(): self.character_tree.delete(item)
        try:
            report_path = Path(self.output_var.get()) / "analysis.json"
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
            speech_stats = character_speech_stats(report)
        except (OSError, ValueError, json.JSONDecodeError):
            speech_stats = {}
        ordered = sorted(self.characters.items(),
                         key=lambda pair: (pair[0] == "__narrator__",
                                           -speech_stats.get(pair[0].casefold(), (0, 0.0))[0],
                                           pair[0].casefold()))
        for name, item in ordered:
            reference = item.get("voice_reference", "")
            valid = bool(reference and (ROOT / reference).is_file()) if reference and not Path(reference).is_absolute() else bool(reference and Path(reference).is_file())
            detection = item.get("detection", {})
            if detection.get("review_required"):
                status = "Revisar"
            elif valid:
                status = "Pronto"
            elif item.get("mode", "original") == "original":
                status = "Original"
            else:
                status = "Voz ausente"
            speeches, weight = speech_stats.get(name.casefold(), (0, 0.0))
            weight_text = f"{weight * 100:.1f}%".replace(".", ",")
            self.character_tree.insert("", "end", iid=name, text=name, values=(speeches, weight_text,
                item.get("mode", "original"), item.get("gender", ""),
                item.get("age_group", ""), Path(reference).name if reference else "", status))
        self._refresh_preview_options()

    def _select_character(self, _: Any = None) -> None:
        selected = self.character_tree.selection()
        if not selected: return
        name = selected[0]
        item = self.characters[name]
        self.char_name.set(name)
        aliases = item.get("aliases", [])
        self.char_aliases.set(aliases if isinstance(aliases, str) else ", ".join(aliases))
        self.char_mode.set(item.get("mode", "original"))
        self.char_gender.set(item.get("gender", ""))
        self.char_age.set(item.get("age_group", ""))
        self.char_voice.set(item.get("voice_reference", ""))
        self.char_pitch.set(float(item.get("pitch_shift", 0)))

    def _clear_character(self) -> None:
        self.char_name.set(""); self.char_aliases.set(""); self.char_mode.set("original"); self.char_gender.set("")
        self.char_age.set(""); self.char_voice.set(""); self.char_pitch.set(0)
        self.character_tree.selection_remove(self.character_tree.selection())

    def _save_character(self, *, show_message: bool = True) -> None:
        name = self.char_name.get().strip()
        mode = self.char_mode.get()
        if not name:
            messagebox.showerror("Personagem", "Informe o nome do personagem.")
            return
        reference = self.char_voice.get().strip()
        if mode == "convert" and not reference:
            messagebox.showerror("Referência necessária", "O modo convert exige uma referência de voz.")
            return
        current = dict(self.characters.get(name, {}))
        current["mode"] = mode
        aliases = list(dict.fromkeys(alias.strip() for alias in self.char_aliases.get().split(",") if alias.strip()))
        reserved = {other_name.casefold(): other_name for other_name in self.characters if other_name != name}
        for other_name, item in self.characters.items():
            if other_name != name:
                other_aliases = item.get("aliases", [])
                if isinstance(other_aliases, str):
                    other_aliases = [other_aliases]
                reserved.update({str(alias).casefold(): other_name for alias in other_aliases})
        conflict = next((alias for alias in aliases if alias.casefold() in reserved), None)
        if conflict:
            messagebox.showerror("Alias duplicado", f'"{conflict}" já pertence a {reserved[conflict.casefold()]}.')
            return
        if aliases:
            current["aliases"] = aliases
        else:
            current.pop("aliases", None)
        if current.get("detection", {}).get("automatic"):
            current["detection"]["review_required"] = False
            current["detection"]["reviewed"] = True
        for key, value in (("gender", self.char_gender.get().strip()), ("age_group", self.char_age.get().strip()),
                           ("voice_reference", reference)):
            if value: current[key] = value
            else: current.pop(key, None)
        current["pitch_shift"] = self.char_pitch.get()
        self.characters[name] = current
        atomic_json(CHARACTERS_PATH, self.characters)
        self._refresh_characters()
        if show_message:
            messagebox.showinfo("Personagem", f"{name} foi salvo.")

    def _delete_character(self) -> None:
        name = self.char_name.get().strip()
        if not name or name not in self.characters: return
        if name == "__narrator__":
            messagebox.showerror("Proteção", "O narrador não pode ser excluído.")
            return
        if messagebox.askyesno("Excluir", f"Excluir a configuração de {name}? O áudio continuará original."):
            self.characters.pop(name)
            atomic_json(CHARACTERS_PATH, self.characters)
            self._clear_character(); self._refresh_characters()

    def _import_voice(self) -> None:
        name = self.char_name.get().strip()
        if not name:
            messagebox.showerror("Importar voz", "Preencha primeiro o nome do personagem.")
            return
        source = filedialog.askopenfilename(filetypes=(("Áudio", "*.wav *.mp3 *.m4a *.flac *.opus *.ogg *.aac"), ("Todos", "*.*")))
        if not source: return
        slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_") or "voice"
        target = ROOT / "voices" / f"{slug}_ref.wav"
        try:
            if Path(source).suffix.casefold() == ".wav":
                if Path(source).resolve() != target.resolve():
                    shutil.copy2(source, target)
            else:
                proc = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", source, "-vn", "-ac", "1", "-ar", "44100", str(target)],
                                      capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if proc.returncode: raise RuntimeError(proc.stderr.strip())
            self.char_voice.set(relative_to_root(target))
            self.char_mode.set("convert")
            self._save_character(show_message=False)
            messagebox.showinfo("Voz importada", f"Referência salva para {name}. O modo foi alterado para convert.")
        except Exception as exc:
            messagebox.showerror("Importar voz", str(exc))

    def _play_reference(self) -> None:
        reference = self.char_voice.get().strip()
        path = (ROOT / reference).resolve() if reference and not Path(reference).is_absolute() else Path(reference)
        if not reference or not path.is_file():
            messagebox.showwarning("Referência", "Este personagem ainda não possui uma referência de voz válida.")
            return
        self._open_path(path)

    def _save_settings(self) -> None:
        try:
            speaker = float(self.setting_vars["speaker"].get())
            alignment = float(self.setting_vars["alignment"].get())
            if not 0 <= speaker <= 1 or not 0 <= alignment <= 1: raise ValueError("Confianças devem ficar entre 0 e 1.")
            data = self.config_data
            data["device"] = self.setting_vars["device"].get()
            data["speaker_confidence_threshold"] = speaker
            data["alignment_confidence_threshold"] = alignment
            data["minimum_segment_duration"] = float(self.setting_vars["duration"].get())
            data["padding_ms"] = int(self.setting_vars["padding"].get())
            data.setdefault("transcription", {}).update(model=self.setting_vars["model"].get(), compute_type=self.setting_vars["compute"].get())
            data.setdefault("voice_conversion", {})["backend"] = self.setting_vars["backend"].get()
            data.setdefault("output", {}).update(format=self.setting_vars["format"].get(), bitrate=self.setting_vars["bitrate"].get())
            data.setdefault("llm", {}).update(enabled=bool(self.setting_vars["llm_enabled"].get()),
                provider=self.setting_vars["llm_provider"].get(), base_url=self.setting_vars["llm_url"].get(), model=self.setting_vars["llm_model"].get())
            atomic_yaml(CONFIG_PATH, data)
            self.run_model.set(data["transcription"]["model"])
            messagebox.showinfo("Configurações", "Configurações salvas.")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Configurações", str(exc))

    def _start(self, command: str, dry_run: bool) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning("Em execução", "Já existe uma tarefa em andamento.")
            return
        source = Path(self.source_var.get())
        if not source.exists():
            messagebox.showerror("Entrada", "Selecione uma pasta ou arquivo de áudio existente.")
            return
        if source.is_dir() and not any(path.suffix.casefold() in SUPPORTED for path in source.iterdir()):
            messagebox.showerror("Entrada", "A pasta selecionada não contém arquivos de áudio suportados.")
            return
        selected = self._selected_audio()
        if source.is_dir() and not selected:
            messagebox.showerror("Capítulos", "Selecione pelo menos um capítulo na lista.")
            return
        book = Path(self.book_var.get()) if self.book_var.get().strip() else None
        if book and not book.is_file():
            messagebox.showerror("Livro", "O arquivo de livro selecionado não existe.")
            return
        if command == "process" and not dry_run:
            try:
                load_characters(CHARACTERS_PATH, project_root=ROOT,
                    allow_shared=bool(self.config_data.get("allow_shared_voice_references", True)), require_references=True)
            except ConfigurationError as exc:
                messagebox.showerror("Configuração de vozes", str(exc))
                self.notebook.select(self.characters_tab)
                return
            if not messagebox.askyesno("Processar", f"Iniciar a conversão de {len(selected)} capítulo(s)? Trechos incertos serão preservados."):
                return
        args = [sys.executable, "-u", str(ROOT / "main.py"), command, str(source), "--config", str(CONFIG_PATH),
                "--characters", str(CHARACTERS_PATH), "--output", self.output_var.get(), "--cache", str(ROOT / "cache"),
                "--language", self.run_language.get(), "--model", self.run_model.get()]
        if book: args.extend(["--book-text", str(book)])
        if source.is_dir():
            for path in selected:
                args.extend(["--include", path.name])
        if dry_run: args.append("--dry-run")
        self.task_kind = "pipeline"
        self.last_command = command
        self.characters_before_task = set(self.characters)
        self.task_started = time.monotonic()
        self.progress_detail.set("Preparando arquivos…")
        for iid, path in self.chapter_paths_by_iid.items():
            values = list(self.chapter_tree.item(iid, "values"))
            values[2] = "Aguardando" if self.audio_selection[str(path)] else "Ignorado"
            self.chapter_tree.item(iid, values=values)
        self.log.delete("1.0", "end")
        self._log("Executando: " + " ".join(f'"{arg}"' if " " in arg else arg for arg in args[2:]) + "\n\n")
        self.status.configure(text="● Processando", foreground=ACCENT)
        self.progress.configure(mode="determinate", maximum=100, value=0)
        for button in self.run_buttons[:3]: button.configure(state="disabled")
        threading.Thread(target=self._worker, args=(args,), daemon=True).start()

    def _worker(self, args: list[str]) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=flags)
            assert self.process.stdout
            for line in self.process.stdout: self.events.put(("log", line))
            code = self.process.wait()
            self.events.put(("done", code))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "log": self._handle_log(value)
                elif event == "done": self._finished(int(value))
                elif event == "error": self._log(f"ERRO: {value}\n"); self._finished(1)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _finished(self, code: int) -> None:
        self.progress.stop()
        for button in self.run_buttons[:3]: button.configure(state="normal")
        if code == 0:
            self.status.configure(text="● Concluído", foreground=SUCCESS)
            if getattr(self, "task_kind", "pipeline") == "pipeline":
                self.progress.configure(mode="determinate", value=100)
                self.progress_detail.set("Concluído")
                if self.last_command == "analyze":
                    self._sync_detected_characters(Path(self.output_var.get()) / "analysis.json")
                    self.characters = self._read_characters()
                    self._refresh_characters()
                    added = sorted(set(self.characters) - getattr(self, "characters_before_task", set()))
                else:
                    added = []
                self._log("\nProcessamento concluído. Abra o relatório para revisar.\n")
                detail = f"\n\n{len(added)} personagem(ns) foram adicionados automaticamente." if added else ""
                messagebox.showinfo("Concluído", "Tarefa concluída. O relatório está na pasta de saída." + detail)
            elif self.task_kind == "preview":
                generated = getattr(self, "pending_preview_paths", {})
                if not generated or not all(path.is_file() for path in generated.values()):
                    self.status.configure(text="● Erro", foreground=DANGER)
                    self.preview_paths = {}
                    messagebox.showerror("Falha na prévia", "A tarefa terminou sem produzir os dois arquivos de áudio.")
                    return
                self.preview_paths = generated
                self.preview_original_button.configure(state="normal")
                self.preview_converted_button.configure(state="normal")
                self._log("\nPrévia concluída. Use os botões A/B para comparar.\n")
                messagebox.showinfo("Prévia pronta", "As amostras original e convertida estão prontas para ouvir.")
            else:
                self._log("\nDiagnóstico concluído.\n")
        else:
            self.status.configure(text="● Erro", foreground=DANGER)
            if getattr(self, "task_kind", "") == "preview":
                self.preview_paths = {}
                self.preview_original_button.configure(state="disabled")
                self.preview_converted_button.configure(state="disabled")
            messagebox.showerror("Falha", "A tarefa falhou. Consulte o painel de logs.")

    def _cancel(self) -> None:
        if self.process and self.process.poll() is None and messagebox.askyesno("Cancelar", "Interromper a tarefa? Os caches concluídos serão mantidos."):
            self.process.terminate()
            self._log("\nCancelamento solicitado.\n")

    def _check_gpu(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning("Em execução", "Aguarde a tarefa atual terminar.")
            return
        self.task_kind = "gpu"
        self.notebook.select(self.process_tab)
        self.log.delete("1.0", "end")
        args = [sys.executable, "-u", str(ROOT / "check_gpu.py")]
        threading.Thread(target=self._worker, args=(args,), daemon=True).start()
        self.status.configure(text="● Verificando", foreground=ACCENT)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)

    def _open_report(self) -> None:
        report = Path(self.output_var.get()) / "report.html"
        if not report.is_file(): messagebox.showwarning("Relatório", "Nenhum report.html foi gerado ainda.")
        else: self._open_path(report)

    @staticmethod
    def _open_path(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True) if path.suffix == "" else None
        os.startfile(path)  # type: ignore[attr-defined]

    def _log(self, text: str) -> None:
        self.log.insert("end", text)
        self.log.see("end")

    def _handle_log(self, value: str) -> None:
        self._log(value)
        match = PROGRESS_PATTERN.search(value)
        if match and self.task_kind == "pipeline":
            percent = min(100.0, max(0.0, float(match.group(1))))
            self.progress.configure(value=percent)
            self.status.configure(text=f"● {percent:.1f}%", foreground=ACCENT)
            elapsed = time.monotonic() - getattr(self, "task_started", time.monotonic())
            remaining = elapsed * (100 - percent) / percent if percent > 0 else 0
            chapter = CHAPTER_PATTERN.search(value)
            detail = chapter.group(4) if chapter else "Processando"
            self.progress_detail.set(f"{detail} • restante aproximado {clock(remaining)}")
        chapter = CHAPTER_PATTERN.search(value)
        if chapter and self.task_kind == "pipeline":
            filename, stage = chapter.group(3), chapter.group(4)
            for iid, path in self.chapter_paths_by_iid.items():
                if path.name == filename:
                    values = list(self.chapter_tree.item(iid, "values"))
                    values[2] = "Concluído" if "concluído" in stage or "checkpoint" in stage else stage.capitalize()
                    self.chapter_tree.item(iid, values=values)
                    self.chapter_tree.see(iid)
                    break

    def _close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Sair", "Há uma tarefa em andamento. Interromper e sair?"): return
            self.process.terminate()
        self.destroy()


def main() -> None:
    os.chdir(ROOT)
    App().mainloop()


if __name__ == "__main__":
    main()

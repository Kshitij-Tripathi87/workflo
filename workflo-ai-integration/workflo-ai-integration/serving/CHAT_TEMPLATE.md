# Extracted from Ollama's published Modelfile for
# qwen2.5-coder:7b-instruct-q4_K_M (blob 1e65450c3067).
#
# This is the chat template the live --deep-test / --aggressive-test pipeline
# already uses via Ollama. model_router._build_prompt() must stay compatible
# with this — do not invent a different template without re-checking
# `ollama show qwen2.5-coder:7b-instruct-q4_K_m --modelfile`.
#
# Base model lock (MMVP): stay on Qwen2.5-Coder 7B Instruct Q4_K_M until a
# held-out eval proves a different base is worth the image rebuild. The
# earlier "Qwen3-Coder" suggestion is aspirational; production today is 2.5.
#
# Minimal turn shape (what model_router emits):
#   <|im_start|>system\n{system}<|im_end|>\n
#   <|im_start|>user\n{user}<|im_end|>\n
#   <|im_start|>assistant\n
#
# Full Ollama Go template (for reference / FIM / tools):

{{- if .Suffix }}<|fim_prefix|>{{ .Prompt }}<|fim_suffix|>{{ .Suffix }}<|fim_middle|>
{{- else if .Messages }}
{{- if or .System .Tools }}<|im_start|>system
{{- if .System }}
{{ .System }}
{{- end }}
{{- if .Tools }}

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:

<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> with NO other text. Do not include any backticks or ```json.

<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
{{- end }}<|im_end|>
{{ end }}
{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 -}}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{ if .Content }}{{ .Content }}
{{- else if .ToolCalls }}<tool_call>
{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
{{ end }}</tool_call>
{{- end }}{{ if not $last }}<|im_end|>
{{ end }}
{{- else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{ end }}
{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
{{ end }}
{{- end }}
{{- else }}
{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
{{ end }}{{ .Response }}{{ if .Response }}<|im_end|>{{ end }}

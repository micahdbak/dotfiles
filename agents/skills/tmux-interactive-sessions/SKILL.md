---
name: tmux-interactive-sessions
description: Drive persistent interactive terminal sessions from a non-interactive shell tool using tmux - SSH chains, REPLs, TUIs, interactive build/install scripts, long-running commands. Use when a task needs a terminal that keeps state between shell calls.
---

# TMUX Interactive Sessions

Operating persistent, interactive terminal sessions from an AI agent, using
nothing but ordinary shell command execution and tmux.

An agent's shell tool is transactional: run a command, collect output, return.
That cannot drive software that keeps state between invocations - SSH
sessions, REPLs, debuggers, TUIs, servers - because the process would die
with the tool call. tmux solves this: it runs a server that owns
pseudo-terminals (ptys) independent of any caller. The agent stays detached
and drives everything through the tmux CLI from plain shell calls.

All tmux behavior below was verified against **tmux 3.7c** by running it.
Where a statement depends on the environment (shell flavor, remote hosts) it
is marked as such. Untested behavior is not presented as verified.

## 0. The operational rules

1. **Know what is in the foreground before sending input.** The same
   `send-keys` reaches a shell, a REPL, a TUI, or a remote program through
   SSH; the foreground program decides what the keys mean. Verify with
   `pane_current_command` (diagnostic only - section 3) and a capture.
2. **Submitted, echoed, output-seen, completed, and succeeded are different
   states.** Confirm each explicitly (section 4). A captured echo is not
   execution; output is not completion.
3. **Use the completion-record protocol** (section 2) for every command that
   matters: a unique per-invocation directory, a status record published
   atomically when execution finishes, and bounded polling of that record.
   Screen markers are a best-effort fallback (section 2.3) - conventions,
   not proof.
4. **Poll with conditions and a bound.** Every wait has a timeout branch
   that inspects; a timeout is never, by itself, a reason to resubmit.
5. **An uncertain result must not be automatically resubmitted.** A missing
   record, a truncated capture, or a lost session does not tell you what
   ran. Verify side effects first (section 7).
6. **Send multi-word commands as one argument.** `send-keys` does NOT
   insert spaces between arguments (section 1, SEND). One quoted string,
   or explicit `Space` keys.
7. **Redirect long output to files, not scrollback.** Scrollback is bounded
   (2000 lines by default) and long sent lines can be truncated in
   rendering (section 1, HISTORY). Exception: interactive programs must
   keep their prompts on screen (section 5.6).
8. **One owner per pane.** Concurrent senders silently destroy each other's
   input. One agent per socket, one task per session; check for human
   attachment and coordinate ownership before sending (section 6).
9. **Never send secrets through send-keys.** Typed secrets land in
   scrollback, captures, and pipe logs. Configure key-based SSH and sudoers
   before the session starts (section 7).
10. **The agent never attaches.** Attaching requires a tty; it is a
    human action (section 6).

## 1. Command reference by operation

Verified commands, grouped by intent. Aliases exist; full names shown.

### CREATE

```bash
tmux has-session -t work 2>/dev/null || tmux new-session -d -s work -x 200 -y 50
```

- `-d` detached (required: attaching from a non-tty fails with
  `open terminal failed: not a terminal`, verified).
- `-x 200 -y 50` sets pane size (detached default is 80x24 - cramped in
  captures). Resizable later: `tmux resize-window -t work:0 -x 100 -y 30`
  (verified).
- Initial program is a shell; a command argument replaces it
  (`tmux new-session -d -s bench 'top'`).
- The first `new-session` starts the tmux server; it exits when the last
  session dies. Sessions die with the machine.

### SEND

```bash
tmux send-keys -t work 'cd ~/project && git status' Enter
tmux send-keys -t work C-c                      # control key
tmux send-keys -t work 'q'                      # a bare key to a TUI
tmux send-keys -t work -l 'Enter'               # literal text, not key name
```

- Arguments are sent consecutively, in order, **with no separator**
  (verified: `echoAB`). `Enter`, `Space`, `Escape`, `C-c`, `C-d`, `Up`,
  `Down`, `NPage`, `PPage` are key names; everything else is typed as text.
- `Enter` must be its own token to execute the line. `-l` disables key-name
  lookup (verified: `-l 'Enter'` types the word).
- Keys go to the pane's foreground program. There is no "run this command"
  abstraction - only typing.

### READ

```bash
tmux capture-pane -t work -p                    # visible screen, plain text
tmux capture-pane -t work -p -S -30             # last 30 lines incl. history
tmux capture-pane -t work -p -J -S -50          # join soft-wrapped lines
```

- `-p` prints to stdout, escape sequences stripped (`-e` keeps colors).
- Line numbers: `0` = first visible line; negatives = scrollback; `-S -` =
  from the start of history; `-E` = end line.
- Blank lines and trailing spaces are real; trim with `grep -v '^$'`.

### HISTORY

```bash
tmux capture-pane -t work -p -S -               # entire scrollback
tmux capture-pane -t work -p -S -100 -E -10     # a specific range
tmux display-message -p -t work '#{history_size}'
```

- Scrollback default 2000 lines (`history-limit`); overflow is permanent
  (verified: after 5000 lines, the first ~2990 are gone).
- Scrollback survives TUI use: content echoed before an alternate-screen
  program is intact after it exits, and TUI redraws do not pollute history
  (verified with `top`, `less`).

### SEARCH

```bash
tmux capture-pane -t work -p -S - | grep -n 'ERROR'
tmux capture-pane -t work -p -S - | sed -n '/Traceback/,+5p'
tmux capture-pane -t work -p -S - | awk '/Total:/ {print $NF}'
```

Unix tools compose freely. Anchor on exact per-invocation IDs; unanchored
matches hit stale lines.

### WAIT

See section 2 (record files) and section 4 (states). The shape:

```bash
for i in $(seq 1 60); do
  [ -f /tmp/tmux-run-$M/rc ] && break
  sleep 2
done
[ -f /tmp/tmux-run-$M/rc ] && echo "rc=$(cat /tmp/tmux-run-$M/rc)" \
  || echo "TIMEOUT - inspect"
```

The inter-iteration `sleep 2` is the poll interval - that is not the
anti-pattern; the anti-pattern is a single unconditional sleep standing in
for a check.

### STATUS

```bash
tmux has-session -t work 2>/dev/null && echo exists || echo gone
tmux list-sessions                              # names + creation times
tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} #{pane_current_command}'
tmux display-message -p -t work '#{pane_id} #{pane_pid} #{pane_current_command} #{pane_current_path}'
```

- `pane_id` is `%N` (verified `%0`), stable, and a valid target
  (`tmux send-keys -t %0 ...`).
- `pane_current_command` is the foreground process **of the pane itself**
  (verified across zsh/python3/top). Diagnostic only: under SSH it reports
  `ssh`; remote programs are invisible. Prompts and records beat metadata.
- `pane_pid` is the pane's first process.
- `#{session_attached}` shows whether any client is attached (verified 0
  while agent-driven; 1 when a human attaches).

### ATTACH (human-only)

```bash
tmux attach-session -t work        # from the HUMAN's terminal
tmux detach-client -s work         # detach a human client; session survives
```

- The agent cannot attach (verified: `open terminal failed: not a
  terminal`). A human attaches, interacts, detaches (their prefix + `d`);
  the agent's session and processes continue.

### INTERRUPT

```bash
tmux send-keys -t work C-c
```

- Verified: interrupts a running command in the pane (and an in-flight SSH
  attempt); prompt returns; session lives on. Repeat for programs that
  ignore SIGINT; `C-z` + `kill %1` as fallback; `kill-pane` as the last
  resort.

### DESTROY

```bash
tmux kill-pane -t work.1          # one pane
tmux kill-window -t work:1        # one window
tmux kill-session -t work         # session + its panes' processes
tmux kill-server                  # everything on this socket
```

- Killing a session kills its panes' processes (verified: an in-pane
  `sleep` was gone after `kill-session`) - but see section 6: processes
  that detached themselves (nohup, daemon) survive.

## 2. The completion-record protocol

The reliable way to run a command in a persistent shell and know what
happened.

### The invocation directory

The agent generates a **unique directory** for the invocation and keeps its
path in its own task notes - the ID is never re-derived by grepping
scrollback:

```bash
M=/tmp/tmux-run-$RANDOM-$$
tmux send-keys -t work "mkdir -m 700 $M && <command>; s=\$?; echo \$s > $M/rc.part && mv $M/rc.part $M/rc" Enter
```

- `mkdir` is atomic: two invocations cannot share a directory, so there is
  no collision and nothing pre-existing to delete (deleting a possibly
  live record is avoided by design - verified pattern).
- `mkdir -m 700` keeps the directory private (0700) - records, statuses,
  and logs are not world-readable.
- The status record is published **atomically**: `.part` then `mv`. A
  reader sees the record absent or complete, never half-written.
- Verified: records appear exactly when execution finishes (`rc=0` for
  success, `rc=7` for a specific failure, including for silent commands
  with no output).
- Durable across independent shell tool calls: the sending call notes the
  directory; any later call polls and reads. The agent's notes plus the
  record are the state.

```bash
# poll (any later tool call) - bounded, with a real timeout outcome
for i in $(seq 1 60); do
  [ -f $M/rc ] && break
  sleep 2
done
if [ -f $M/rc ]; then echo "rc=$(cat $M/rc)"; else echo "TIMEOUT - inspect"; fi
```

Redirect the command's output into the same private directory
(`<command> > $M/out.log 2>&1`); read it after completion. Complete output,
no scrollback limits, survives session death.

### Timeout branches: the three cases to distinguish

When the record has not appeared after the bound, one of three things is
true - inspect, then act:

1. **Still running** - the pane shows the program busy. Wait longer or
   `C-c`, then inspect partial output; status uncertain.
2. **The shell died before writing the record** - verified signature:
   record absent, `pane_dead=1` (with `pane_dead_signal` showing the
   signal; a shell killed by its own command leaves no record). The
   command's side effects are unknown - verify externally before any
   retry.
3. **The session is gone** - `has-session` fails. Same conclusion as case
   2, plus the loss of the pane itself (section 6).

None of these is "the command failed with rc=N" - and none is a reason to
resubmit without verification.

### Remote commands (through SSH)

Two distinct situations:

- **One-shot remote command** (agent sends `ssh host 'cmd'`): the record
  directory would be created on the remote machine, where the agent cannot
  poll. Instead, the command emits a **status marker into the pane** when
  it finishes, and the marker includes the status digit - the element only
  execution can produce - so the echoed input line cannot match:

  ```bash
  M=/tmp/tmux-run-$RANDOM-$$      # noted agent-side
  tmux send-keys -t work "ssh user@host.example.com 'remote-command; r=\$?; echo RC-${M##*/}-\$r'" Enter
  ```

  ```bash
  for i in $(seq 1 60); do
    tmux capture-pane -t work -p | grep -qE "RC-${M##*/}-[0-9]+$" && break
    sleep 2
  done
  tmux capture-pane -t work -p | grep -E "RC-${M##*/}-[0-9]+$" | tail -1
  ```

- **An established SSH session** (a remote shell is already the pane's
  foreground): commands are typed at the remote shell; the same marker
  mechanics apply, with the remote shell evaluating the status. Distinguish
  the situations by reading the prompt (section 5.1).

**Markers are conventions, not authentication.** They prove a matching line
was rendered - not that a well-behaved application produced it. A program
that emits plausible marker text (or an attacker-controlled program) defeats
the check. The record-file form is stronger (a file the agent's own command
wrote); for hostile or untrusted software, verify effects out-of-band (the
output files, the service state), not the terminal text.

Remote output goes to a remote file; read it by `cat`/`tail` through the
pane, or `scp` it, once the record confirms completion. Nested chains: the
same applies at the innermost machine that runs the command; the pane shows
the innermost shell's output.

Screen-marker reliability caveat (verified): a long sent command can wrap
and render truncated at the pane width, cutting off a trailing marker
entirely. Prefer records; keep screen-marker commands short.

### Choosing a form

| Situation | Form |
|---|---|
| Agent reads the filesystem the command runs on | record directory |
| Command runs on a remote machine (pane SSH) | remote digit-anchored marker |
| Output needed later, any size | file redirection + record |
| Program prompts mid-run | live on screen + record (section 5.6) |
| Quick throwaway (no side effects) | marker on screen is enough |

## 3. Terminal state and output semantics

- **Raw PTY stream** (`pipe-pane`): complete and raw - ANSI codes,
  control chars (verified: 574 bytes of stream for two `echo` commands).
- **Rendered screen** (`capture-pane -p`): what a human sees right now.
- **Scrollback history** (`capture-pane -p -S -N` / `-S -`): bounded,
  text only; overflow is permanent.
- **Alternate screen** (`capture-pane -p` while a TUI runs): the TUI
  frame; no history accumulates in it.
- **Application log files** (plain file tools): complete, structured,
  survive everything.
- **Pane metadata** (`display-message -p '#{...}'`): pid, dead status,
  size, foreground name.

Consequences (verified unless noted):

- **Redraws**: TUIs rewrite the screen in place; capture per frame to watch
  change; no history builds up while a TUI runs.
- **Carriage returns**: progress bars (`\r` updates) collapse to one line
  per screen row; intermediate states are invisible in captures.
- **ANSI escapes**: absent from `capture-pane`, present in `pipe-pane`
  output. Parse files or captures, not raw streams.
- **Wrapping**: long lines wrap across screen rows; `-J` joins them in
  captures (verified). Sent lines wrap too and can render truncated
  (section 2).
- **Dimensions**: `-x`/`-y` at creation, `resize-window` later; TUIs
  relayout to fit.
- **Bounded scrollback**: verified - 5000 lines filled the limit (~1973
  lines retained) and the first ~2990 were lost permanently.

Keeping agent input small: capture, then filter (`tail`, `grep`, `sed`,
`awk`) before consuming. Reading "new output since interaction X": redirect
to a file and diff/line-count against a noted position; scrollback has no
reliable "since" marker.

## 4. Synchronization: the nine states

Not interchangeable. Name the state before acting.

1. **Input submitted** - `send-keys` returned. Says nothing about delivery.
2. **Input echoed** - the capture shows the typed line (or a program's
   rendering of it). Delivered, not executed.
3. **Expected output observed** - evidence of execution, not completion.
4. **Command completed** - the record appeared (file or digit-anchored
   marker).
5. **Command succeeded/failed** - the record carries the status. Completion
   AND status.
6. **Foreground process exited** - `#{pane_dead}=1` with
   `pane_dead_status`/`pane_dead_signal` (pane's initial process only;
   child programs use the record protocol - verified both behaviors).
7. **A wait timed out** - the bound was hit. A failure state: run the
   three-case inspection (section 2); never an automatic resubmit.
8. **Session lost** - `has-session` fails or `no server running` (verified
   messages). Recreate deliberately; see section 6 for the process-lifetime
   fine print.
9. **State uncertain** - capture contradicts expectations. Stop; inspect;
   do not act on assumptions (section 7).

Precise detection exists for local shell commands (records), remote commands
via pane markers, and pane-process exits. For arbitrary application state,
completion is only ever inferred (prompt return, output pattern, silence) -
treat it as state 9 unless the application documents its own marker.

## 5. Operating interactive software

### 5.1 SSH sessions and nested connections (verified)

```bash
tmux has-session -t work 2>/dev/null || tmux new-session -d -s work -x 200 -y 50
tmux send-keys -t work 'ssh -o ConnectTimeout=8 -p 2222 user@bastion.example.com' Enter
# wait for the bastion prompt - bounded, condition-based (prompt is
# environment-specific; anchor on the hostname/user part)
for i in $(seq 1 20); do
  tmux capture-pane -t work -p | grep -q 'user@bastion' && break
  sleep 1
done
tmux capture-pane -t work -p | grep -v '^$' | tail -1
# "[user@bastion ~]$"                            <- arrived (read the prompt!)
tmux send-keys -t work 'ssh user@10.0.1.6' Enter
# ...same bounded wait...
tmux send-keys -t work 'cd ~/project && git log --oneline -1' Enter
sleep 4                                          # short, then verify
tmux capture-pane -t work -p | grep -v '^$' | tail -2
# "user@internal:~/project$ ... git log --oneline -1"
# "1a2b3c4 (HEAD -> main) Some commit message"   <- remote output captured
```

1. **Read the prompt after every hop.** The last capture line is the
   current prompt; a hostname/user mismatch means keys went somewhere
   unexpected. If the expected prompt has not appeared, capture again
   after another interval - never assume, never retype.
2. **Each `exit` unwinds exactly one hop** (verified: inner -> bastion ->
   local).
3. **The completion protocol works through the chain** - the innermost
   shell evaluates the status; poll the pane (digit-anchored) for remote
   commands.
4. **Disconnects and failures leave the pane intact** (verified: connection
   refused + mid-handshake `C-c` both return to the usable shell).
   Reconnect by sending `ssh` again. Never assume a frozen pane is
   disconnected - capture first.
5. **Auth**: configure key-based SSH before the session starts. A password
   prompt would render in the pane - and a typed password would land in
   scrollback and captures. Coordinate with a human instead (section 7).
6. Long remote work: run remote-side into a remote file (`... >
   /tmp/out.log 2>&1`), then `tail`/`cat` it through the pane or `scp` it
   back. Immune to scrollback limits and disconnects.

### 5.2 Persistent REPLs (verified)

```bash
tmux send-keys -t work 'python3' Enter
sleep 2
# later tool call: define state
tmux send-keys -t work 'x = 41 + 1' Enter
tmux send-keys -t work 'print(x)' Enter          # -> "42"
# later tool call: an error does not end the REPL
tmux send-keys -t work '1/0' Enter               # Traceback; '>>>' returns
```

- State (variables, imports) persists across tool calls (verified).
- Errors return to the prompt; the REPL is fine (verified).
- Multi-statement work: write a snippet to a file, then
  `exec(open('/tmp/s.py').read())` - and have the snippet end with
  `print('DONE')` (or write its own completion record) for reliable
  completion detection.
- Exit deliberately (`exit()`); kill the pane if wedged.

### 5.3 Interactive TUIs (verified with top and less)

```bash
tmux send-keys -t work 'top' Enter
sleep 2
tmux capture-pane -t work -p | head -5           # the rendered frame
tmux send-keys -t work '1'                       # a navigation/option key
sleep 1
tmux capture-pane -t work -p | sed -n '3,5p'     # verify the change
tmux send-keys -t work 'q'                       # quit
sleep 1
# prompt is back; scrollback before the TUI is intact (verified)
```

- The same `send-keys` that ran shell commands now sends **keyboard
  shortcuts**: `q` means quit inside top/less and is literal text at a
  shell prompt. Foreground context decides meaning.
- TUIs redraw in place: capture per frame; nothing accumulates.
- Safe exit: quit key, verify the prompt returned, then continue. `C-c`
  fallback; the session survives either way.
- Prefer non-interactive forms when they exist (`top -b -n1`), but genuine
  TUIs are fully operable.

### 5.4 Long-running programs

```bash
M=/tmp/tmux-run-$RANDOM-$$
tmux send-keys -t work "mkdir -m 700 $M && ./bench --long-run > $M/out.log 2>&1; s=\$?; echo \$s > $M/rc.part && mv $M/rc.part $M/rc" Enter
```

- Poll the record; read `$M/out.log` for progress (`tail`, line counts) and
  for the final status.
- Interact while it runs if it reads stdin (send keys; capture its prompts).
- Interrupt with `C-c` (verified - session survives); the log shows how far
  it got. A record without `rc` after an interrupt means the program was
  killed mid-run - status uncertain; verify effects before rerunning.
- A program launched this way is the shell's child: `pane_dead` stays 0 on
  its exit - the record is the truth.

### 5.5 Interactive prompts (verified)

```bash
tmux send-keys -t work 'read -p "Enter name: " n; echo "GOT-$n"' Enter
sleep 1
tmux capture-pane -t work -p | tail -1           # "Enter name:"
tmux send-keys -t work 'agent' Enter
sleep 1
# capture: "Enter name: agent" / "GOT-agent"
```

- Recognize the prompt by capturing after the send; answer with the value +
  `Enter`; verify by the program's confirmation output.
- Shell-flavor trap (verified): `read -p` is bash syntax; at a **zsh**
  prompt it fails instantly and the follow-up input runs as a shell
  command. Identify the pane's shell first; run `bash` explicitly when
  using bash-only syntax.

### 5.6 Interactive scripts: build/install wizards (verified)

Scripts that work, pause for input mid-run, then continue - `./configure`
wrappers, build scripts with confirmation prompts, installers, menu-based
configurators. Everything above applies, plus four behaviors specific to
them.

**1. Wait on the disjunction: completion record OR prompt.** The polling
loops elsewhere in this document wait for one condition. An interactive
script can end up in either state, so poll for both and handle whichever
arrives:

```bash
M=/tmp/tmux-run-$RANDOM-$$
tmux send-keys -t work "mkdir -m 700 $M && ./build.sh; s=\$?; echo \$s > $M/rc.part && mv $M/rc.part $M/rc" Enter
for i in $(seq 1 60); do
  [ -f $M/rc ] && { echo DONE; break; }
  tmux capture-pane -t work -p | grep -qE '\[y/N\]:|\[Y/n\]:' && { echo PROMPT; break; }
  sleep 1
done
```

On PROMPT: capture, read the question, answer it, then re-enter the same
loop - a script may prompt several times before the record appears. The
timeout branch is unchanged (section 2's three cases). Verified: the loop
broke on the prompt after 5s of a run with two 2s work phases, and the
record appeared with `rc=0` after the answer.

**2. Keep the script's output on screen.** Redirecting an interactive
script's output to a file redirects its prompts too - verified: with
`./build.sh > $M/out.log 2>&1`, the `read -p` prompt went to the log, the
pane showed nothing, and the script sat blocked on input looking hung.
Run interactive scripts live on the pane; the record file alone goes to
disk. If the build is too verbose for scrollback, duplicate through `tee`
instead of redirecting:

```bash
tmux send-keys -t work "mkdir -m 700 $M && { ./build.sh 2>&1 | tee $M/out.log; s=\${PIPESTATUS[0]}; }; echo \$s > $M/rc.part && mv $M/rc.part $M/rc" Enter
```

`PIPESTATUS` (not `$?`, which would be tee's status) is **bash-only** -
verified: at a zsh pane it expanded empty and the record carried no
status; zsh needs `\$pipestatus[1]`. Caveat (environment-dependent): with
stdout a pipe, the script's stdout is not a tty, so programs that check
`[ -t 1 ]` may drop colors or prompt text.

**3. Match the answer form to the prompt flavor.** Sending the wrong form
does not fail loudly - it corrupts the NEXT prompt:

- **Line prompts** (`read`, `[y/N]` with Enter expected): send value +
  `Enter`. Pressing `Enter` alone accepts the default (the capital letter
  in `[y/N]`-style prompts) - a safe choice when unsure.
- **Single-key prompts** (`read -n 1`, `less`-style): send the key WITHOUT
  `Enter`. Verified: answering `y` + `Enter` to a `read -n 1` prompt left
  the newline buffered, and the script's second `read -n 1` consumed it
  instantly as an empty answer. Answering with the bare key worked.
- **bash `select` menus** (`1) debug  2) release`): send the number +
  `Enter` (verified). An invalid or empty answer just redisplays the menu.
- **Full-screen menus** (`whiptail`, `dialog`, `make menuconfig`):
  alternate-screen TUIs - `Up`/`Down` navigate, `Space` toggles, `Enter`
  confirms, `Escape` cancels (verified with whiptail: `Down` moved the
  selection, the frame was capturable, `Escape` exited). Menu text is
  space-padded; filter captures with `grep -v '^[[:space:]]*$'`.

**4. Waiting-for-input vs busy is an inference.** A blocked script and a
compiling script can both show a static screen. Heuristic: capture twice
a few seconds apart; a stable screen whose last non-blank line is
prompt-shaped (ends in `:`, `?`, `[y/N]`, a menu cursor) means waiting.
When in doubt, treat as state 9 (section 4): inspect more, send nothing.

Interrupting a script mid-run (`C-c`) can leave partial build artifacts;
the no-record-after-interrupt rule from 5.4 applies - verify effects
before rerunning. If a script demands a password (sudo), that is section
7 territory: preconfigure `NOPASSWD` or hand to a human; never send it.
Many scripts also have a non-interactive mode (`-y`, `--assume-yes`,
`DEBIAN_FRONTEND=noninteractive`) - prefer it when the task allows
counting on defaults.

## 6. Session lifecycle, ownership, and concurrency

### Ownership: prevent silent input loss

Two senders into one pane corrupt each other - verified: two concurrent
`send-keys` calls and one command **vanished silently** (never echoed, never
executed). Convention:

- **One socket per agent**: `tmux -L agent-<name> ...` isolates the agent's
  servers from other agents and from a human's default tmux (verified:
  separate sockets list and die independently).
- **One session per task** inside the socket.
- **Check before sending**: `tmux has-session -t work` and
  `tmux display-message -p -t work '#{session_attached}'` (0 = no human
  attached).
- **Multi-agent coordination via lock**: create atomically -
  `mkdir /tmp/tmux-lock-work 2>/dev/null` (mkdir is atomic; the loser
  knows) - and record the owner inside it:
  `echo $$ > /tmp/tmux-lock-work/owner`.
  Limitations, explicitly: a lock **does not** coordinate a human typing
  in an attached client (use `#{session_attached}` for that); a lock
  **can become stale** when its holder crashes without cleanup - check
  the recorded pid's liveness (`ps -p $(cat .../owner)`) and treat a
  dead holder's lock as reclaimable; ownership **across tool calls** is
  the agent's own bookkeeping - the lock directory and its contents are
  the durable record; release with `rmdir` when done.

### Panes: parallel terminals in one session (verified)

```bash
tmux split-window -t work -h -c '~/project'
tmux list-panes -t work -F '#{pane_id} #{pane_index} #{pane_current_command}'
tmux send-keys -t %1 'tail -f /tmp/server.log' Enter
tmux capture-pane -t %1 -p | tail -5
tmux kill-pane -t %1
```

Each pane is an independent pty with its own program and history. Verified
addressing forms: `%id` (stable) and `session.pane` shorthand (`work.0`,
`work.1`); fully qualified targets are `session:window.pane`. Use one pane
for the program, one for inspecting its effects, one as scratch.

### Humans

- A human may `tmux attach -t work` from their terminal to watch or type;
  `#{session_attached}` reveals it (verified). The agent pauses sends while
  a human is attached unless coordinated; `tmux detach-client -s work`
  detaches them without killing anything.
- Sessions survive the human's SSH disconnects by design.

### Process lifetime: losing a pane is not losing the work

- **Pane processes die with the pane** (verified: an in-pane `sleep` was
  gone after `kill-session`).
- **Self-detached processes survive** (verified): a `nohup`-ed child was
  still alive after `kill-session`, reparented. Daemons and background
  jobs keep running.
- **Remote processes**: a process running over SSH dies when the
  connection dies (SIGHUP to the remote shell's children) *unless* it was
  started with `nohup`/`setsid`/as a daemon or under tmux *on the remote*.
  Environment-dependent; verify remotely before assuming either way.

The rule: **after any pane, session, or connection loss, treat affected
work's status as uncertain until verified** - by the completion record if
one exists, otherwise by checking the effects (files, services, remote
process lists). When checking process lists, remember `pgrep -f`
self-matches the probing command's own cmdline (verified).

### Cleanup

Kill panes/sessions when a task ends; `kill-server` for the workspace.
Keep evidence-bearing log files; remove lock directories and records.

## 7. Error handling and operational safety

Diagnose before acting. **The resubmission rule: an uncertain result is
never automatically resubmitted.** Inspect first; verify; only then decide.

- **Timeout on a record.** Run the three-case inspection (section 2):
  busy, dead shell, or dead session. Busy: wait or `C-c`, then inspect.
  Dead shell: side effects unknown, verify externally. None of these
  means "retry now".
- **Session gone** (`has-session` fails, or `no server running`). Pane
  processes died, but detached or remote processes may live on
  (section 6). Verify effects before re-running.
- **Output truncated** (check: does the record say `rc=N`? how large is
  `#{history_size}`?). Truncated output is NOT execution failure: if the
  record says completed, do not rerun - fetch output another way (file,
  remote `cat`, `scp`).
- **Wrong prompt or host in capture** (compare the prompt line). Keys
  went to the wrong layer; unwind (`exit`) or reconnect; send nothing
  else first.
- **Program unresponsive** (capture; check `pane_current_command`).
  `C-c`; if ignored, `C-z` + `kill`; `kill-pane` as the last resort.
  Detached children may survive any of these.
- **Echo without execution** (check the foreground program). Keys went
  into a program's stdin, or into the wrong pane; re-target.
- **Input vanished** (a competing sender; run the ownership check,
  section 6). Re-establish ownership; re-send only the lost command,
  after confirming it never ran.
- **Shell died mid-command** (record absent + `pane_dead=1`, the
  verified signature). Side effects unknown; verify out-of-band before
  any retry.

Recoverable vs human-required:

- Recoverable: missing session (recreate), timed-out command (inspect,
  possibly retry after verification), failed remote connection
  (reconnect), wrong working directory (`cd` back), interrupted program
  (inspect, restart with care).
- Human-required: authentication the agent cannot have preconfigured,
  permissions outside the agent's scope, destructive operations the task
  did not authorize, repeated unknown crashes.

Secrets and permissions:

- Configure authentication before sessions run (SSH keys, sudoers
  `NOPASSWD` for the specific commands, or a human doing privileged steps).
- If a secret must be typed interactively, a human does it at attach time -
  not through the agent's captures.
- The invocation directory is created private (`-m 700`, verified) - keep
  records and logs there rather than in world-readable `/tmp` files.
- Capture output is a transcript of everything on screen; treat anything
  that appeared there as having entered the agent's context.

## 8. Workflows

### Workflow A: remote administration over nested SSH

```bash
tmux has-session -t ops 2>/dev/null || tmux new-session -d -s ops -x 200 -y 50

# hop 1, bounded wait for the prompt (pattern is environment-specific)
tmux send-keys -t ops 'ssh -p 2222 user@bastion.example.com' Enter
for i in $(seq 1 20); do
  tmux capture-pane -t ops -p | grep -q 'user@bastion' && break
  sleep 1
done
tmux capture-pane -t ops -p | grep -v '^$' | tail -1        # verify hop 1

# hop 2
tmux send-keys -t ops 'ssh user@10.0.1.6' Enter
for i in $(seq 1 20); do
  tmux capture-pane -t ops -p | grep -q 'user@internal' && break
  sleep 1
done
tmux capture-pane -t ops -p | grep -v '^$' | tail -1        # verify hop 2

# diagnostics, each verified by capture
tmux send-keys -t ops 'df -h /' Enter; sleep 2
tmux capture-pane -t ops -p | grep -v '^$' | tail -3

# a long-running remote operation: remote status marker (digit-anchored)
M=/tmp/tmux-run-$RANDOM-$$
tmux send-keys -t ops "M=${M##*/}; ./collect-diagnostics.sh > /tmp/diag.log 2>&1; r=\$?; echo RC-\$M-\$r" Enter
for i in $(seq 1 60); do
  tmux capture-pane -t ops -p | grep -qE "RC-[0-9]+-[0-9]+$" && break
  sleep 2
done
tmux capture-pane -t ops -p | grep -E "RC-[0-9]+-[0-9]+$" | tail -1   # status
tmux send-keys -t ops 'tail -30 /tmp/diag.log' Enter; sleep 2
tmux capture-pane -t ops -p | tail -30                            # results

# leave the connection alive for the next tool call / next day
```

Note the quoting: `$M` is expanded by the agent (the agent's ID);
`\$r`/`\$?` are escaped so the remote shell evaluates them. The echoed
input therefore shows `RC-$M-$r` - unmatchable by the digit-anchored poll.

Success determination: prompt line after each hop (bounded waits);
per-command captures; `RC-<id>-<status>` line for the long operation. The
session persists across tool calls; `has-session -t ops` re-checks before
any later reuse.

### Workflow B: interactive debugging in a REPL

```bash
tmux new-session -d -s dbg -x 200 -y 50
tmux send-keys -t dbg 'python3' Enter; sleep 2
tmux send-keys -t dbg 'import mymodule' Enter; sleep 1
tmux send-keys -t dbg 'state = mymodule.load()' Enter; sleep 2
tmux capture-pane -t dbg -p | tail -4                 # traceback? dump?
# on error: repair and continue in the SAME session
tmux send-keys -t dbg 'state = mymodule.load_repaired()' Enter; sleep 2
tmux send-keys -t dbg 'state.summary()' Enter; sleep 1
tmux capture-pane -t dbg -p | tail -6
```

State survives tool calls and errors; iterate without restarting.

### Workflow C: concurrent development

```bash
tmux new-session -d -s dev -x 200 -y 50
tmux split-window -t dev -h
tmux send-keys -t dev.0 './server --port 8080 > /tmp/server.log 2>&1' Enter
# readiness: bounded poll of the log, not a fixed sleep
for i in $(seq 1 30); do
  grep -qi listening /tmp/server.log 2>/dev/null && break
  sleep 1
done
tmux send-keys -t dev.1 'curl -s localhost:8080/health' Enter; sleep 1
tmux capture-pane -t dev.1 -p | tail -2               # function check
# later: inspect through pane 0 or the log; interrupt dev.0 with C-c when done
```

### Workflow D: human-agent collaboration

```bash
tmux new-session -d -s review -x 200 -y 50
tmux send-keys -t review './app --interactive' Enter
for i in $(seq 1 20); do
  tmux capture-pane -t review -p | grep -qi 'started' && break
  sleep 1
done
# tell the human: "tmux attach -t review" from their terminal
tmux display-message -p -t review '#{session_attached}'   # 1 = human attached
tmux capture-pane -t review -p | tail -8                  # agent observes
# agent pauses sends while attached; human detaches; agent resumes
```

### Workflow E: interactive build script

```bash
tmux has-session -t build 2>/dev/null || tmux new-session -d -s build -x 200 -y 50

# launch live on screen (prompts must stay visible) + completion record
M=/tmp/tmux-run-$RANDOM-$$
tmux send-keys -t build "mkdir -m 700 $M && ./build.sh; s=\$?; echo \$s > $M/rc.part && mv $M/rc.part $M/rc" Enter

# the answer loop: wait for record OR prompt, act, repeat
while true; do
  for i in $(seq 1 60); do
    [ -f $M/rc ] && break
    tmux capture-pane -t build -p | grep -qE '\[y/N\]:|\[Y/n\]:' && break
    sleep 1
  done
  [ -f $M/rc ] && { echo "FINISHED rc=$(cat $M/rc)"; break; }
  tmux capture-pane -t build -p | grep -v '^[[:space:]]*$' | tail -3   # read the question
  tmux send-keys -t build 'y' Enter          # line prompt -> value + Enter
  # (single-key read -n 1 prompt -> bare key, NO Enter; section 5.6)
done

tmux capture-pane -t build -p -S -50 | grep -iE 'error|warning' | tail -10
```

Success determination: the record's `rc`, not the absence of visible
errors - capture greps are truncated views. A verbose build swaps the
launch line for the `tee` variant (section 5.6); a menu-based configurator
uses arrow keys/`Enter` inside the same answer loop.

## 9. Verification notes

- tmux version tested: **3.7c** (check with `tmux -V`).
- Verified live: session create/kill/has-session; sizes and
  `resize-window`; send-keys key names, `-l`, argument joining, `C-c`
  interrupt (shell command and in-flight SSH); capture-pane
  `-p`/`-S`/`-E`/`-J`; `#{pane_id}` stability and `%id` targeting;
  `#{pane_current_command}` across zsh/python3/top;
  `#{pane_dead}`/`pane_dead_status`/`pane_dead_signal` under
  `remain-on-exit`; `pipe-pane` capture and raw-ANSI noise; the
  completion-record protocol (unique invocation directory, atomic
  `.part`+`mv` publication, success / silent command / failing command /
  shell-killed-mid-command cases, cross-tool-call durability); echoed-input
  false completion (pre-expanded marker) and digit-anchored mitigation;
  render truncation of long sent lines; competing concurrent senders
  (silent input loss); REPL persistence and error recovery; TUI
  send/capture/quit (top, less); scrollback preservation across TUI use
  and permanent loss on overflow (5000 lines); `read -p` prompt handling
  (bash) and its zsh failure; nested SSH chain (two hops, remote output
  capture, per-hop `exit`); missing-session and dead-server messages;
  `-L` socket isolation and `kill-server`; kill-session killing pane
  processes; nohup'd processes surviving kill-session;
  `#{session_attached}` states; completion detection across independent
  shell tool calls; disjunctive prompt-or-record waiting against a
  mid-run-prompting script; prompt capture lost when an interactive
  script's output is redirected; `tee`+`PIPESTATUS` transcript capture
  (and its empty expansion under zsh); `read -n 1` answered by a bare key
  and the stray-Enter bleed into the next prompt; `select` menus answered
  by number + Enter; whiptail menu navigation (Down/Enter/Escape) and
  frame capture; `pgrep -f` self-matching the probing command's cmdline.
- Environment-dependent (tmux behavior verified; hosts/timings
  illustrative): SSH handshake and prompt formats, remote shell flavors,
  poll-interval tuning.
- Not verified, do not assume: multi-client concurrent typing beyond
  `#{session_attached}` detection; TUIs beyond top/less; fish or other
  shell syntax; control mode (`-C`); remote nohup behavior over a live SSH
  connection.

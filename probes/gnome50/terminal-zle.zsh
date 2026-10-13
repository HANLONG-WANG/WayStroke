# Disposable ZLE capability probe: never evaluate captured lines as commands.
setopt NO_BEEP
bindkey -e
integer expansions=0
waystroke-expand() {
  if [[ $LBUFFER == abc ]]; then
    LBUFFER=2003
    (( expansions++ ))
  fi
}
waystroke-space() { waystroke-expand; zle .self-insert }
waystroke-enter() { waystroke-expand; zle .accept-line }
zle -N waystroke-space
zle -N accept-line waystroke-enter
bindkey ' ' waystroke-space
root=$1
for stage in space enter; do
  printf '%s' "$stage" > "$root/zle-stage"
  line=''
  vared -p "Fixture $stage: " line
  printf '%s' "$line" > "$root/zle-$stage.txt"
done
printf '%s' 'ime' > "$root/zle-stage"
line=''
vared -p 'Fixture IME: ' line
printf '%s' "$line" > "$root/zle-ime.txt"
printf '%s' 'secret' > "$root/zle-stage"
secret=''
read -rs 'secret?Disposable hidden input: '
printf '\n'
printf '%s' "${#secret}" > "$root/zle-secret-length"
unset secret
printf '%s' 'external-password' > "$root/zle-stage"
/usr/bin/python3 "${0:A:h}/terminal-fixture.py" "$root" password-fast
printf '%s' "$expansions" > "$root/zle-expansions"
printf '%s' 'complete' > "$root/zle-stage"
sleep 20

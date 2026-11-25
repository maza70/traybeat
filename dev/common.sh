
#!/usr/bin/env bash
BLACK='\033[0;30m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[1;35m'
CYAN='\033[0;36m'
WHITE='\033[0;37m'

LIGHT_RED='\033[0;91m'
LIGHT_GREEN='\033[0;92m'
LIGHT_YELLOW='\033[0;93m'
LIGHT_BLUE='\033[0;94m'
LIGHT_MAGENTA='\033[0;95m'
LIGHT_CYAN='\033[0;96m'
NC='\033[0m'


print_header() {
    printf "${MAGENTA}${SCRIPT_NAME}: ${YELLOW}%s${NC}\n" "$*"
}
print_error() {
    printf "${MAGENTA}${SCRIPT_NAME}: ${RED}%s${NC}\n" "$*"  >&2
}
print_info() {
    printf "${MAGENTA}${SCRIPT_NAME}: ${GREEN}%s${NC}\n" "$*"
}

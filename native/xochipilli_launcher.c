// std includes for launcher (also keeps clangd happy)
#include <Python.h>
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void die(const char *msg) {
    fprintf(stderr, "[xochipilli-launcher] %s\n", msg);
    system(
        "/usr/bin/osascript -e "
        "'display alert \"Xochipilli\" message \"ランチャ起動に失敗しました。Logs/Xochipilli を確認。\" as critical' "
        ">/dev/null 2>&1");
    exit(1);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    char exe_path[PATH_MAX];
    uint32_t size = sizeof(exe_path);
    if (_NSGetExecutablePath(exe_path, &size) != 0) {
        die("cannot resolve executable path");
    }
    char resolved[PATH_MAX];
    if (!realpath(exe_path, resolved)) {
        strncpy(resolved, exe_path, sizeof(resolved) - 1);
        resolved[sizeof(resolved) - 1] = '\0';
    }

    const char *root =
        "/path/to/xochipilli";
    if (chdir(root) != 0) {
        die("chdir project root failed");
    }

    setenv("VIRTUAL_ENV",
           "/path/to/xochipilli/.venv",
           1);
    unsetenv("PYTHONPATH");
    unsetenv("PYTHONHOME");
    setenv("PYTHONUNBUFFERED", "1", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);

    /* Dock launches swallow stdout — force session log */
    {
        const char *home = getenv("HOME");
        char logpath[PATH_MAX];
        if (home && home[0]) {
            snprintf(logpath, sizeof(logpath),
                     "%s/Library/Logs/Xochipilli/session.log", home);
        } else {
            snprintf(logpath, sizeof(logpath),
                     "/tmp/xochipilli-session.log");
        }
        FILE *lf = fopen(logpath, "a");
        if (lf) {
            fprintf(lf, "==== mach-o launcher pid=%d exe=%s ====\n", getpid(),
                    resolved);
            fflush(lf);
            dup2(fileno(lf), STDOUT_FILENO);
            dup2(fileno(lf), STDERR_FILENO);
            /* lf intentionally not fclose'd — owns stdout */
        }
    }

    wchar_t *program = Py_DecodeLocale(resolved, NULL);
    if (!program) {
        die("Py_DecodeLocale failed");
    }
    Py_SetProgramName(program);

    Py_Initialize();
    if (!Py_IsInitialized()) {
        die("Py_Initialize failed");
    }

    int rc = PyRun_SimpleString(
        "import sys, os\n"
        "root = r'/path/to/xochipilli'\n"
        "venv_site = root + r'/.venv/lib/python3.11/site-packages'\n"
        "sys.path.insert(0, root)\n"
        "if venv_site not in sys.path:\n"
        "    sys.path.insert(0, venv_site)\n"
        "os.chdir(root)\n"
        "import desktop_app\n"
        "raise SystemExit(desktop_app.main())\n");

    if (Py_FinalizeEx() < 0) {
        return 120;
    }
    PyMem_RawFree(program);
    return rc != 0 ? rc : 0;
}

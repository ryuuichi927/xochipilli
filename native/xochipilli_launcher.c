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

/* Read Contents/Resources/ProjectRoot (one line = absolute project root). */
static int read_project_root(const char *exe_resolved, char *out, size_t out_sz) {
    char res_path[PATH_MAX];
    char dir[PATH_MAX];
    strncpy(dir, exe_resolved, sizeof(dir) - 1);
    dir[sizeof(dir) - 1] = '\0';
    char *slash = strrchr(dir, '/');
    if (!slash) {
        return -1;
    }
    *slash = '\0'; /* .../Contents/MacOS */
    slash = strrchr(dir, '/');
    if (!slash) {
        return -1;
    }
    *slash = '\0'; /* .../Contents */
    snprintf(res_path, sizeof(res_path), "%s/Resources/ProjectRoot", dir);

    FILE *f = fopen(res_path, "r");
    if (!f) {
        return -1;
    }
    if (!fgets(out, (int)out_sz, f)) {
        fclose(f);
        return -1;
    }
    fclose(f);
    /* trim CR/LF and trailing spaces */
    size_t n = strlen(out);
    while (n > 0 && (out[n - 1] == '\n' || out[n - 1] == '\r' || out[n - 1] == ' ' ||
                     out[n - 1] == '\t')) {
        out[--n] = '\0';
    }
    return (n > 0 && out[0] == '/') ? 0 : -1;
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

    char root[PATH_MAX];
    if (read_project_root(resolved, root, sizeof(root)) != 0) {
        die("cannot read Contents/Resources/ProjectRoot");
    }
    if (chdir(root) != 0) {
        die("chdir project root failed");
    }

    char venv[PATH_MAX];
    snprintf(venv, sizeof(venv), "%s/.venv", root);
    setenv("VIRTUAL_ENV", venv, 1);
    unsetenv("PYTHONPATH");
    unsetenv("PYTHONHOME");
    setenv("PYTHONUNBUFFERED", "1", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
    /* Dock launches often leave C locale → Python print crashes on JA paths */
    setenv("PYTHONIOENCODING", "utf-8", 1);
    setenv("LANG", "en_US.UTF-8", 0);
    setenv("LC_ALL", "en_US.UTF-8", 0);
    setenv("LC_CTYPE", "en_US.UTF-8", 0);

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
            fprintf(lf, "==== mach-o launcher pid=%d exe=%s root=%s ====\n", getpid(),
                    resolved, root);
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

    /* Build Python bootstrap with runtime root (no hardcoded user path). */
    char py[PATH_MAX * 3];
    snprintf(
        py, sizeof(py),
        "import sys, os\n"
        "root = r'%s'\n"
        "venv_site = root + r'/.venv/lib/python3.11/site-packages'\n"
        "sys.path.insert(0, root)\n"
        "if venv_site not in sys.path:\n"
        "    sys.path.insert(0, venv_site)\n"
        "os.chdir(root)\n"
        "import desktop_app\n"
        "raise SystemExit(desktop_app.main())\n",
        root);

    int rc = PyRun_SimpleString(py);

    if (Py_FinalizeEx() < 0) {
        return 120;
    }
    PyMem_RawFree(program);
    return rc != 0 ? rc : 0;
}

/*
 * force_fullscreen.c
 * Waits for the Boosteroid window to appear, then sends it an EWMH
 * _NET_WM_STATE_FULLSCREEN ClientMessage so it fills the Gamescope display.
 *
 * Build: gcc force_fullscreen.c -lX11 -o boosteroid-fullscreen
 * Run:   boosteroid-fullscreen &   (before or just after launching Boosteroid)
 */
#define _GNU_SOURCE
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* Recursively search the window tree for a window whose WM_CLASS or title
 * contains "boosteroid" (case-insensitive). */
static Window find_window(Display *dpy, Window root)
{
    Window parent, *children = NULL;
    unsigned int nchildren = 0;
    Window result = 0;

    if (!XQueryTree(dpy, root, &root, &parent, &children, &nchildren))
        return 0;

    for (unsigned int i = 0; i < nchildren && !result; i++) {
        XClassHint hint;
        if (XGetClassHint(dpy, children[i], &hint)) {
            if ((hint.res_name  && strcasestr(hint.res_name,  "boosteroid")) ||
                (hint.res_class && strcasestr(hint.res_class, "boosteroid"))) {
                result = children[i];
            }
            XFree(hint.res_name);
            XFree(hint.res_class);
        }
        if (!result) {
            char *name = NULL;
            if (XFetchName(dpy, children[i], &name) && name &&
                strcasestr(name, "boosteroid"))
                result = children[i];
            if (name) XFree(name);
        }
        if (!result)
            result = find_window(dpy, children[i]);
    }

    if (children) XFree(children);
    return result;
}

int main(void)
{
    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) return 1;

    Window root       = DefaultRootWindow(dpy);
    Atom   state_atom = XInternAtom(dpy, "_NET_WM_STATE", False);
    Atom   fs_atom    = XInternAtom(dpy, "_NET_WM_STATE_FULLSCREEN", False);

    /* Poll up to 30 s for the window to appear. */
    Window win = 0;
    for (int i = 0; i < 60 && !win; i++) {
        win = find_window(dpy, root);
        if (!win) usleep(500000);
    }

    if (!win) {
        fprintf(stderr, "boosteroid-fullscreen: window not found\n");
        XCloseDisplay(dpy);
        return 1;
    }

    /* Give the window a moment to finish initialising before we fullscreen it. */
    usleep(300000);

    XEvent ev;
    memset(&ev, 0, sizeof(ev));
    ev.xclient.type         = ClientMessage;
    ev.xclient.display      = dpy;
    ev.xclient.window       = win;
    ev.xclient.message_type = state_atom;
    ev.xclient.format       = 32;
    ev.xclient.data.l[0]    = 1;       /* _NET_WM_STATE_ADD */
    ev.xclient.data.l[1]    = (long)fs_atom;
    ev.xclient.data.l[2]    = 0;
    ev.xclient.data.l[3]    = 1;       /* source: normal application */

    XSendEvent(dpy, root, False,
               SubstructureNotifyMask | SubstructureRedirectMask, &ev);
    XFlush(dpy);
    XCloseDisplay(dpy);
    return 0;
}

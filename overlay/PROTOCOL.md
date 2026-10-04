# HonestHands overlay protocol

The warning UI is a separate helper process. The app talks to it with one JSON
object per line: commands on the helper's stdin, events on its stdout.
Any platform can supply its own helper (e.g. a Windows one) that speaks this.

## App -> helper
    {"cmd":"show","id":"<str>","hard":false,"title":"Hold on a second",
     "context":"CS101 / Essay 2 · Claude","reason":"...","rule":"...","quote":"...",
     "tip":"...","source":"AI judge","allowSend":true,"allowLater":true}
    {"cmd":"hide"}
    {"cmd":"quit"}

## Helper -> app
    {"event":"ready"}
    {"event":"choice","id":"<str>","choice":"edit"|"send_anyway"|"later"}

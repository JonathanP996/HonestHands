"""The warning popup on Windows: the same card as the Mac's native one, drawn natively (WPF, which ships with Windows).

Why not a web page: a web window can't be see-through on Windows, so it showed up as a big pale box. WPF windows can have a
real per-pixel transparent background, rounded corners, soft shadows and smooth animations, so this is the closest thing Windows
has to SwiftUI. It runs in this same process on its own UI thread; the layout is the XAML text below.

It sits top-right over everything and never takes the keyboard focus (so the AI app you were typing in stays in front); the keys
Esc / Enter / Ctrl+Enter are handled by the keyboard watcher while the card is open.

Same interface as the Mac's overlay_client: show(payload, on_choice), checking(), ok(), hide(), is_open(), choose()."""
import ctypes
import ctypes.wintypes as wt
import threading


def _log(msg):
    try:
        import watcher_win
        watcher_win.diag('overlay: ' + msg)
    except Exception:
        pass


GWL_EXSTYLE = -20
WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x08000000, 0x00000080, 0x00000008
SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOMOVE = 0x10, 0x1, 0x2
HWND_TOPMOST = -1
CARD_W = 396

DARK = dict(Card='#F21B2421', Ink='#F3F1EA', Muted='#9EF3F1EA', Faint='#66F3F1EA', Line='#1AF3F1EA')
LIGHT = dict(Card='#F5FFFDF9', Ink='#1C2420', Muted='#9E1C2420', Faint='#6B1C2420', Line='#1A1C2420')
ACCENT, LIME = '#E65C57', '#A9B620'

# One declarative layout, like a SwiftUI view. Colours that change with light/dark are DynamicResource; the rest is fixed.
XAML = r'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="HonestHands Overlay" WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ShowInTaskbar="False" Topmost="True" ShowActivated="False" ResizeMode="NoResize" Focusable="False"
        SizeToContent="Height" Width="440" UseLayoutRounding="True" SnapsToDevicePixels="True"
        FontFamily="Segoe UI Variable Text, Segoe UI" TextOptions.TextFormattingMode="Display">
  <Window.Resources>
    <SolidColorBrush x:Key="Card" Color="#F21B2421"/>
    <SolidColorBrush x:Key="Ink" Color="#F3F1EA"/>
    <SolidColorBrush x:Key="Muted" Color="#9EF3F1EA"/>
    <SolidColorBrush x:Key="Faint" Color="#66F3F1EA"/>
    <SolidColorBrush x:Key="Line" Color="#1AF3F1EA"/>
    <SolidColorBrush x:Key="Accent" Color="#E65C57"/>
    <SolidColorBrush x:Key="Lime" Color="#A9B620"/>
    <ControlTemplate x:Key="Btn" TargetType="Button">
      <Border x:Name="Bd" Background="{TemplateBinding Background}" CornerRadius="11" Padding="10,9"
              RenderTransformOrigin="0.5,0.5" Cursor="Hand">
        <Border.RenderTransform><ScaleTransform x:Name="Sc"/></Border.RenderTransform>
        <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
      </Border>
      <ControlTemplate.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Trigger.EnterActions><BeginStoryboard><Storyboard>
            <DoubleAnimation Storyboard.TargetName="Sc" Storyboard.TargetProperty="ScaleX" To="1.03" Duration="0:0:0.15"/>
            <DoubleAnimation Storyboard.TargetName="Sc" Storyboard.TargetProperty="ScaleY" To="1.03" Duration="0:0:0.15"/>
          </Storyboard></BeginStoryboard></Trigger.EnterActions>
          <Trigger.ExitActions><BeginStoryboard><Storyboard>
            <DoubleAnimation Storyboard.TargetName="Sc" Storyboard.TargetProperty="ScaleX" To="1" Duration="0:0:0.15"/>
            <DoubleAnimation Storyboard.TargetName="Sc" Storyboard.TargetProperty="ScaleY" To="1" Duration="0:0:0.15"/>
          </Storyboard></BeginStoryboard></Trigger.ExitActions>
          <Setter TargetName="Bd" Property="Opacity" Value="0.9"/>
        </Trigger>
        <Trigger Property="IsPressed" Value="True"><Setter TargetName="Bd" Property="Opacity" Value="0.78"/></Trigger>
      </ControlTemplate.Triggers>
    </ControlTemplate>
  </Window.Resources>

  <Grid x:Name="Root" Margin="14,12,14,28">
    <StackPanel HorizontalAlignment="Right">

      <Border x:Name="PillCheck" Visibility="Collapsed" Opacity="0" HorizontalAlignment="Right" CornerRadius="20" Padding="15,10"
              Margin="0,0,0,10" Background="{DynamicResource Card}" BorderBrush="{DynamicResource Line}" BorderThickness="1">
        <Border.Effect><DropShadowEffect BlurRadius="24" ShadowDepth="8" Direction="270" Opacity="0.4" Color="Black"/></Border.Effect>
        <Border.RenderTransform><TranslateTransform x:Name="PillCheckT"/></Border.RenderTransform>
        <StackPanel Orientation="Horizontal">
          <Ellipse x:Name="Spin" Width="14" Height="14" Stroke="{DynamicResource Muted}" StrokeThickness="2" StrokeDashArray="14 4.8"
                   Margin="0,0,9,0" RenderTransformOrigin="0.5,0.5"><Ellipse.RenderTransform><RotateTransform x:Name="SpinR"/></Ellipse.RenderTransform></Ellipse>
          <TextBlock Text="Checking with your professor…" FontSize="12.5" Foreground="{DynamicResource Ink}" VerticalAlignment="Center"/>
        </StackPanel>
      </Border>

      <Border x:Name="PillOk" Visibility="Collapsed" Opacity="0" HorizontalAlignment="Right" CornerRadius="20" Padding="13,10,15,10"
              Margin="0,0,0,10" Background="{DynamicResource Card}" BorderBrush="#8CA9B620" BorderThickness="1">
        <Border.Effect><DropShadowEffect BlurRadius="24" ShadowDepth="8" Direction="270" Opacity="0.4" Color="Black"/></Border.Effect>
        <Border.RenderTransform><TranslateTransform x:Name="PillOkT"/></Border.RenderTransform>
        <StackPanel Orientation="Horizontal">
          <Viewbox Width="16" Height="16" Margin="0,0,9,0"><Canvas Width="24" Height="24">
            <Ellipse Width="19" Height="19" Canvas.Left="2.5" Canvas.Top="2.5" Fill="#2EA9B620" Stroke="#A9B620" StrokeThickness="2.2"/>
            <Polyline Points="7.5,12.5 10.5,15.5 16.5,9" Stroke="#A9B620" StrokeThickness="2.6" StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round"/>
          </Canvas></Viewbox>
          <TextBlock Text="You’re good, sending it" FontSize="12.5" Foreground="{DynamicResource Ink}" VerticalAlignment="Center"/>
        </StackPanel>
      </Border>

      <Border x:Name="Card" Visibility="Collapsed" Opacity="0" Width="396" CornerRadius="24" Padding="18"
              Background="{DynamicResource Card}" BorderThickness="1">
        <Border.BorderBrush>
          <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
            <GradientStop Color="#99E65C57" Offset="0"/><GradientStop Color="#1AF3F1EA" Offset="0.6"/>
          </LinearGradientBrush>
        </Border.BorderBrush>
        <Border.Effect><DropShadowEffect BlurRadius="40" ShadowDepth="16" Direction="270" Opacity="0.45" Color="Black"/></Border.Effect>
        <Border.RenderTransform><TranslateTransform x:Name="CardT"/></Border.RenderTransform>
        <StackPanel>
          <Grid>
            <Grid.ColumnDefinitions><ColumnDefinition Width="Auto"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
            <Grid Width="34" Height="34" Margin="0,0,12,0">
              <Ellipse Fill="#33E65C57"/>
              <Ellipse x:Name="Rp1" Stroke="#8CE65C57" StrokeThickness="2" Opacity="0" RenderTransformOrigin="0.5,0.5"/>
              <Ellipse x:Name="Rp2" Stroke="#8CE65C57" StrokeThickness="2" Opacity="0" RenderTransformOrigin="0.5,0.5"/>
              <Ellipse x:Name="Rp3" Stroke="#8CE65C57" StrokeThickness="2" Opacity="0" RenderTransformOrigin="0.5,0.5"/>
              <Viewbox x:Name="Tri" Width="17" Height="17" RenderTransformOrigin="0.5,0.5">
                <Canvas Width="24" Height="24">
                  <Polygon Points="12,3.5 21.5,20 2.5,20" Fill="{DynamicResource Accent}" Stroke="{DynamicResource Accent}" StrokeThickness="2.6" StrokeLineJoin="Round"/>
                  <Line X1="12" Y1="9.6" X2="12" Y2="14.4" Stroke="#F21B2421" StrokeThickness="2.2" StrokeStartLineCap="Round" StrokeEndLineCap="Round"/>
                  <Ellipse Width="2.4" Height="2.4" Canvas.Left="10.8" Canvas.Top="16.2" Fill="#F21B2421"/>
                </Canvas>
              </Viewbox>
            </Grid>
            <StackPanel Grid.Column="1" VerticalAlignment="Center">
              <TextBlock x:Name="Title" FontSize="16" FontWeight="SemiBold" Foreground="{DynamicResource Ink}"/>
              <TextBlock x:Name="Ctx" FontSize="11.5" Foreground="{DynamicResource Muted}" TextTrimming="CharacterEllipsis" Margin="0,1,0,0"/>
            </StackPanel>
          </Grid>

          <Border x:Name="Body" Height="0" Opacity="0" ClipToBounds="True">
            <StackPanel Margin="0,14,0,0">
              <TextBlock x:Name="R1" FontSize="13.5" LineHeight="20" TextWrapping="Wrap" Foreground="{DynamicResource Ink}"/>
              <TextBlock x:Name="R2" FontSize="12.5" LineHeight="18" TextWrapping="Wrap" Margin="0,10,0,0" Foreground="{DynamicResource Ink}"/>
              <Grid x:Name="R3" Margin="0,10,0,0">
                <Grid.ColumnDefinitions><ColumnDefinition Width="Auto"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                <Border Width="3" CornerRadius="2" Background="#B3E65C57"/>
                <TextBlock x:Name="QuoteText" Grid.Column="1" Margin="9,0,0,0" FontFamily="Georgia" FontStyle="Italic" FontSize="12.5" LineHeight="18"
                           TextWrapping="Wrap" Foreground="{DynamicResource Muted}"/>
              </Grid>
              <Grid x:Name="R4" Margin="0,10,0,0">
                <Grid.ColumnDefinitions><ColumnDefinition Width="Auto"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                <Viewbox Width="12" Height="12" Margin="0,3,7,0" VerticalAlignment="Top"><Canvas Width="24" Height="24">
                  <Path Fill="{DynamicResource Accent}" Data="M 12,2 A 7,7 0 0 0 8,14.7 L 8,17 A 1,1 0 0 0 9,18 L 15,18 A 1,1 0 0 0 16,17 L 16,14.7 A 7,7 0 0 0 12,2 Z M 10,20 L 14,20 L 14,21 A 2,2 0 0 1 10,21 Z"/>
                </Canvas></Viewbox>
                <TextBlock x:Name="TipText" Grid.Column="1" FontSize="12.5" LineHeight="18" TextWrapping="Wrap" Foreground="{DynamicResource Accent}"/>
              </Grid>
              <TextBlock x:Name="R5" FontSize="10.5" Margin="0,10,0,0" Foreground="{DynamicResource Faint}"/>
              <StackPanel x:Name="R6" Margin="0,10,0,0">
                <Grid>
                  <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                  <Button x:Name="BtnEdit" Template="{StaticResource Btn}" Background="{DynamicResource Lime}" Foreground="#D9000000"
                          Focusable="False" IsTabStop="False" FontSize="13" FontWeight="SemiBold" Margin="0,0,4,0">
                    <StackPanel Orientation="Horizontal">
                      <TextBlock x:Name="EditLabel" Text="Edit my message"/>
                      <TextBlock Text="  ↩" FontSize="11" FontWeight="Normal" Opacity="0.55" VerticalAlignment="Center"/>
                    </StackPanel>
                  </Button>
                  <Button x:Name="BtnSend" Grid.Column="1" Template="{StaticResource Btn}" Background="{DynamicResource Accent}" Foreground="White"
                          Focusable="False" IsTabStop="False" FontSize="13" FontWeight="SemiBold" Margin="4,0,0,0">
                    <StackPanel Orientation="Horizontal">
                      <TextBlock Text="Send it now"/>
                      <TextBlock Text="  Ctrl ↩" FontSize="11" FontWeight="Normal" Opacity="0.6" VerticalAlignment="Center"/>
                    </StackPanel>
                  </Button>
                </Grid>
                <StackPanel x:Name="NoteRow" Orientation="Horizontal" Margin="0,8,0,0">
                  <Viewbox Width="11" Height="11" Margin="0,1,6,0" VerticalAlignment="Center"><Canvas Width="24" Height="24">
                    <Path Stroke="{DynamicResource Faint}" StrokeThickness="2" StrokeLineJoin="Round" Data="M 6,3 L 15,3 L 19,7 L 19,21 L 6,21 Z"/>
                    <Path Stroke="{DynamicResource Faint}" StrokeThickness="2" StrokeStartLineCap="Round" StrokeEndLineCap="Round" Data="M 9.5,13 L 15.5,13 M 9.5,17 L 15.5,17"/>
                  </Canvas></Viewbox>
                  <TextBlock x:Name="NoteText" FontSize="11" Foreground="{DynamicResource Faint}" VerticalAlignment="Center"/>
                </StackPanel>
              </StackPanel>
            </StackPanel>
          </Border>
        </StackPanel>
      </Border>
    </StackPanel>
  </Grid>
</Window>
'''


def _dark_mode():
    """True unless Windows is set to light app mode (the same choice the Mac card follows)."""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
        return winreg.QueryValueEx(k, 'AppsUseLightTheme')[0] == 0
    except Exception:
        return True


class WinOverlay:
    def __init__(self, resource=None):
        self._cb = None
        self._open = False          # a warning card is showing (not just a pill)
        self._allow_send = False
        self._closing = False
        self._shown = False
        self._styled = False
        self._ready = threading.Event()
        self._failed = False
        self._timer = None
        self._theme = None          # tests can force DARK / LIGHT
        self._disp = None
        self._start()

    # ------------------------------------------------------------ the popup interface the shared code expects
    def is_open(self):
        return self._open

    def owns_point(self, x, y):
        return False

    def show(self, payload, on_choice):
        self._cb = on_choice
        self._open = True
        self._allow_send = bool(payload.get('allowSend', not payload.get('hard')))
        if not self._call(lambda: self._show_block(payload)):
            return self._fallback(payload)
        return True

    def checking(self):
        return self._call(self._show_checking)

    def ok(self):
        return self._call(self._show_ok)

    def hide(self):
        self._open = False
        self._call(self._hide_now)

    def choose(self, choice):
        """Called by the keyboard watcher when Esc / Enter / Ctrl+Enter is pressed while the card is open."""
        if choice == 'send_anyway' and not self._allow_send:
            choice = 'edit'
        if not self._call(lambda: self._pick(choice)):
            self._chosen(choice)
        return True

    # ------------------------------------------------------------ the UI thread
    def _start(self):
        try:
            import clr
            for n, tok in (('PresentationFramework', '31bf3856ad364e35'), ('PresentationCore', '31bf3856ad364e35'),
                           ('WindowsBase', '31bf3856ad364e35'), ('System.Xaml', 'b77a5c561934e089')):
                clr.AddReference(f'{n}, Version=4.0.0.0, Culture=neutral, PublicKeyToken={tok}')
            from System.Threading import ApartmentState, Thread, ThreadStart

            def run():
                try:
                    self._build()
                    self._ready.set()
                    from System.Windows.Threading import Dispatcher
                    Dispatcher.Run()
                except Exception as e:
                    self._failed = True
                    self._ready.set()
                    _log(f'ui thread failed: {e!r}')
            th = Thread(ThreadStart(run))
            th.SetApartmentState(ApartmentState.STA)          # WPF windows must live on an STA thread
            th.IsBackground = True
            th.Start()
        except Exception as e:
            self._failed = True
            self._ready.set()
            _log(f'could not start: {e!r}')

    def _call(self, fn):
        """Run fn on the UI thread (without waiting). False if the native window isn't available."""
        if not self._ready.wait(8) or self._failed or self._disp is None:
            return False
        try:
            from System import Action
            self._disp.BeginInvoke(Action(lambda: self._safe(fn)))
            return True
        except Exception as e:
            _log(f'dispatch failed: {e!r}')
            return False

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:
            _log(f'{getattr(fn, "__name__", "step")} failed: {e!r}')

    # ------------------------------------------------------------ building
    def _build(self):
        from System.Windows.Markup import XamlReader
        from System.Windows.Threading import Dispatcher
        self._disp = Dispatcher.CurrentDispatcher
        self._win = XamlReader.Parse(XAML)
        names = ('Root PillCheck PillCheckT PillOk PillOkT Spin SpinR Card CardT Rp1 Rp2 Rp3 Tri Title Ctx Body R1 R2 R3 R4 R5 R6 '
                 'QuoteText TipText BtnEdit BtnSend EditLabel NoteRow NoteText').split()
        self.e = {n: self._win.FindName(n) for n in names}
        self.e['BtnEdit'].Click += lambda s, a: self._pick('edit')
        self.e['BtnSend'].Click += lambda s, a: self._pick('send_anyway')

    # ------------------------------------------------------------ small animation helpers
    def _br(self, argb):
        from System.Windows.Media import BrushConverter
        return BrushConverter().ConvertFromString(argb)

    def _ease(self, kind='quint', out=True, amp=0.35):
        from System.Windows.Media.Animation import BackEase, CubicEase, EasingMode, QuinticEase
        e = {'quint': QuinticEase, 'cubic': CubicEase, 'back': BackEase}[kind]()
        e.EasingMode = EasingMode.EaseOut if out else EasingMode.EaseIn
        if kind == 'back':
            e.Amplitude = amp
        return e

    def _anim(self, target, prop, to, ms, frm=None, ease=None, begin=0, done=None, repeat=None):
        from System import TimeSpan
        from System.Windows import Duration
        from System.Windows.Media.Animation import DoubleAnimation, RepeatBehavior
        a = DoubleAnimation()
        if frm is not None:
            a.From = float(frm)
        a.To = float(to)
        a.Duration = Duration(TimeSpan.FromMilliseconds(ms))
        if ease is not None:
            a.EasingFunction = ease
        if begin:
            a.BeginTime = TimeSpan.FromMilliseconds(begin)
        if repeat:
            a.RepeatBehavior = RepeatBehavior.Forever if repeat == 'forever' else RepeatBehavior(float(repeat))
        if done:
            a.Completed += lambda s, e: done()
        target.BeginAnimation(prop, a)

    def _timeout(self, ms, fn):
        from System import TimeSpan
        from System.Windows.Threading import DispatcherTimer
        t = DispatcherTimer()
        t.Interval = TimeSpan.FromMilliseconds(ms)

        def tick(s, e):
            t.Stop()
            self._safe(fn)
        t.Tick += tick
        t.Start()
        return t

    # ------------------------------------------------------------ states
    def _apply_theme(self):
        pal = self._theme or (DARK if _dark_mode() else LIGHT)
        for k, v in pal.items():
            self._win.Resources[k] = self._br(v)
        self._win.Resources['Accent'] = self._br(ACCENT)
        self._win.Resources['Lime'] = self._br(LIME)

    def _place_and_show(self):
        from System.Windows import SystemParameters
        self._apply_theme()
        wa = SystemParameters.WorkArea
        self._win.Left = wa.Right - self._win.Width + 6        # the card ends up ~8px from the screen edge
        self._win.Top = wa.Top + 2
        if not self._shown:
            self._win.Show()
            self._shown = True
        self._style_once()
        self._raise()

    def _hwnd(self):
        from System.Windows.Interop import WindowInteropHelper
        return int(WindowInteropHelper(self._win).EnsureHandle().ToInt64())

    def _style_once(self):
        """A tool window that never takes focus and floats over everything."""
        if self._styled:
            return
        try:
            u = ctypes.WinDLL('user32', use_last_error=True)
            u.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
            h = self._hwnd()
            u.SetWindowLongPtrW(h, GWL_EXSTYLE, u.GetWindowLongPtrW(h, GWL_EXSTYLE) | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
            self._styled = True
        except Exception as e:
            _log(f'style note: {e!r}')

    def _raise(self):
        try:
            u = ctypes.WinDLL('user32', use_last_error=True)
            u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            u.SetWindowPos(self._hwnd(), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception as e:
            _log(f'raise note: {e!r}')

    def _reset(self):
        """Back to a clean, hidden state (stops every running animation)."""
        from System.Windows import FrameworkElement, UIElement, Visibility
        from System.Windows.Media import RotateTransform, TranslateTransform
        if self._timer is not None:
            try:
                self._timer.Stop()
            except Exception:
                pass
            self._timer = None
        self._closing = False
        e = self.e
        for n in ('PillCheck', 'PillOk', 'Card'):
            e[n].BeginAnimation(UIElement.OpacityProperty, None)
            e[n].Opacity = 0
            e[n].Visibility = Visibility.Collapsed
        for n in ('PillCheckT', 'PillOkT', 'CardT'):
            e[n].BeginAnimation(TranslateTransform.XProperty, None)
            e[n].X = 0
        e['SpinR'].BeginAnimation(RotateTransform.AngleProperty, None)
        e['Body'].BeginAnimation(FrameworkElement.HeightProperty, None)
        e['Body'].BeginAnimation(UIElement.OpacityProperty, None)
        e['Body'].Height = 0
        e['Body'].Opacity = 0

    def _hide_now(self):
        self._reset()
        if self._shown:
            self._win.Hide()
            self._shown = False

    def _slide_in(self, el, tr, ms=550):
        from System.Windows import UIElement, Visibility
        from System.Windows.Media import TranslateTransform
        el.Visibility = Visibility.Visible
        self._anim(tr, TranslateTransform.XProperty, 0, ms, frm=self._win.Width, ease=self._ease('quint'))
        self._anim(el, UIElement.OpacityProperty, 1, 320, frm=0)

    def _show_checking(self):
        from System.Windows.Media import RotateTransform
        self._reset()
        self._place_and_show()
        self._slide_in(self.e['PillCheck'], self.e['PillCheckT'], 500)
        self._anim(self.e['SpinR'], RotateTransform.AngleProperty, 360, 700, frm=0, repeat='forever')

    def _show_ok(self):
        from System.Windows import UIElement, Visibility
        from System.Windows.Media import TranslateTransform
        e = self.e
        if not self._shown:
            self._place_and_show()
        self._anim(e['PillCheck'], UIElement.OpacityProperty, 0, 160)
        e['PillCheck'].Visibility = Visibility.Collapsed
        self._slide_in(e['PillOk'], e['PillOkT'], 500)

        def leave():
            self._anim(e['PillOkT'], TranslateTransform.XProperty, self._win.Width, 480, ease=self._ease('quint', out=False))
            self._anim(e['PillOk'], UIElement.OpacityProperty, 0, 300, done=self._finished)
        self._timer = self._timeout(1400, leave)

    def _finished(self):
        """The 'you're good' pill has slid away."""
        if not self._open:
            self._hide_now()

    def _show_block(self, p, animate=True):
        from System.Windows import FontWeights, FrameworkElement, Size, Thickness, UIElement, Visibility
        from System.Windows.Controls import Grid
        from System.Windows.Documents import Run
        from System.Windows.Media import ScaleTransform, TranslateTransform
        e = self.e
        self._reset()
        hard = bool(p.get('hard'))
        allow = bool(p.get('allowSend', not hard))

        def vis(el, on):
            el.Visibility = Visibility.Visible if on else Visibility.Collapsed

        e['Title'].Text = p.get('title') or ('Message blocked' if hard else 'Hold on a second')
        e['Ctx'].Text = p.get('context') or ''
        vis(e['Ctx'], bool(p.get('context')))
        e['R1'].Text = p.get('reason') or ''
        rule = p.get('rule')
        e['R2'].Inlines.Clear()
        if rule:
            lab = Run('Rule   ')
            lab.FontWeight = FontWeights.SemiBold
            lab.Foreground = self._win.Resources['Muted']
            e['R2'].Inlines.Add(lab)
            e['R2'].Inlines.Add(Run(rule))
        vis(e['R2'], bool(rule))
        e['QuoteText'].Text = '“' + (p.get('quote') or '') + '”'
        vis(e['R3'], bool(p.get('quote')))
        e['TipText'].Text = p.get('tip') or ''
        vis(e['R4'], bool(p.get('tip')))
        e['R5'].Text = 'Checked by the ' + (p.get('source') or 'guard')
        e['EditLabel'].Text = p.get('okLabel') or ('OK, I’ll edit it' if hard else 'Edit my message')
        vis(e['BtnSend'], allow)
        e['BtnEdit'].Margin = Thickness(0, 0, 4 if allow else 0, 0)
        Grid.SetColumnSpan(e['BtnEdit'], 1 if allow else 2)
        e['NoteText'].Text = p['note'] if p.get('note') is not None and 'note' in p else 'Sending it now is recorded in your activity log.'
        vis(e['NoteRow'], allow and bool(e['NoteText'].Text))

        # measure the unfolded body so we can animate to it
        e['Body'].Height = float('nan')
        e['Body'].Measure(Size(CARD_W - 38, float('inf')))
        full = e['Body'].DesiredSize.Height
        rows = [e[n] for n in ('R1', 'R2', 'R3', 'R4', 'R5', 'R6')]
        self._place_and_show()
        vis(e['Card'], True)
        if not animate:
            e['Card'].Opacity = 1
            e['Body'].Opacity = 1
            e['Body'].Height = float('nan')
            for r in rows:
                r.Opacity = 1
            return full
        for r in rows:
            r.Opacity = 0
            r.RenderTransform = TranslateTransform(0, 8)
        self._slide_in(e['Card'], e['CardT'], 550)

        # the alert badge: a bounce, and three ripples
        sc = ScaleTransform(0.3, 0.3)
        e['Tri'].RenderTransform = sc
        for prop in (ScaleTransform.ScaleXProperty, ScaleTransform.ScaleYProperty):
            self._anim(sc, prop, 1, 700, frm=0.3, ease=self._ease('back', amp=0.6), begin=100)
        for i, n in enumerate(('Rp1', 'Rp2', 'Rp3')):
            rp = ScaleTransform(0.9, 0.9)
            e[n].RenderTransform = rp
            for prop in (ScaleTransform.ScaleXProperty, ScaleTransform.ScaleYProperty):
                self._anim(rp, prop, 2.6, 1500, frm=0.9, begin=280 * i, repeat=2)
            self._anim(e[n], UIElement.OpacityProperty, 0, 1500, frm=0.6, begin=280 * i, repeat=2)

        def unfold():
            self._anim(e['Body'], FrameworkElement.HeightProperty, full, 600, frm=0, ease=self._ease('quint'))
            self._anim(e['Body'], UIElement.OpacityProperty, 1, 350, frm=0)
            for i, r in enumerate(rows):
                self._anim(r, UIElement.OpacityProperty, 1, 400, frm=0, begin=50 + 50 * i)
                self._anim(r.RenderTransform, TranslateTransform.YProperty, 0, 400, frm=8, begin=50 + 50 * i, ease=self._ease('cubic'))
        self._timer = self._timeout(280, unfold)         # the card arrives small, then unfolds
        return full

    def _pick(self, choice):
        """The person chose: the card slides away, then the choice is reported."""
        from System.Windows import UIElement
        from System.Windows.Media import TranslateTransform
        if self._closing or not self._open:
            return
        self._closing = True
        e = self.e
        self._anim(e['CardT'], TranslateTransform.XProperty, self._win.Width, 320, ease=self._ease('quint', out=False))
        self._anim(e['Card'], UIElement.OpacityProperty, 0, 280, done=lambda: self._chosen(choice))

    def _chosen(self, choice):
        cb, self._cb = self._cb, None
        self._open = False
        self._call(self._hide_now)
        if cb:
            threading.Thread(target=cb, args=(choice,), daemon=True).start()
        return True

    # ------------------------------------------------------------ if the native window can't start (should not happen)
    def _fallback(self, payload):
        """A plain system dialog, so a flagged message is never silently let through."""
        def ask():
            text = (payload.get('title') or 'Hold on a second') + '\n\n' + (payload.get('reason') or '')
            allow = bool(payload.get('allowSend', not payload.get('hard')))
            if allow:
                r = ctypes.windll.user32.MessageBoxW(0, text + '\n\nYes = Send it now, No = Edit my message', 'HonestHands', 0x4 | 0x30 | 0x40000)
                self._chosen('send_anyway' if r == 6 else 'edit')
            else:
                ctypes.windll.user32.MessageBoxW(0, text, 'HonestHands', 0x0 | 0x30 | 0x40000)
                self._chosen('edit')
        threading.Thread(target=ask, daemon=True).start()
        return True

    # ------------------------------------------------------------ test hook: draw a state to a PNG without showing anything
    def _snapshot(self, path, kind='block', payload=None, dark=True):
        done = threading.Event()
        err = []

        def go():
            try:
                from System import Double
                from System.IO import FileMode, FileStream
                from System.Windows import Rect, Size, Visibility
                from System.Windows.Media import PixelFormats
                from System.Windows.Media.Imaging import BitmapFrame, PngBitmapEncoder, RenderTargetBitmap
                self._theme = DARK if dark else LIGHT
                self._reset()
                self._apply_theme()
                e = self.e
                if kind == 'block':
                    self._open = True
                    self._show_block_static(payload or {})
                elif kind == 'checking':
                    e['PillCheck'].Visibility = Visibility.Visible
                    e['PillCheck'].Opacity = 1
                elif kind == 'ok':
                    e['PillOk'].Visibility = Visibility.Visible
                    e['PillOk'].Opacity = 1
                root = self._win.Content
                root.Background = self._br('#FF7A6F8F' if dark else '#FFD9D4C8')       # a stand-in desktop so the card's edges show
                root.InvalidateMeasure()                    # otherwise the previous state's size is reused
                root.Measure(Size(440, Double.PositiveInfinity))
                root.Arrange(Rect(0, 0, 440, root.DesiredSize.Height))
                root.UpdateLayout()
                w, h = 440, int(root.DesiredSize.Height) + 1
                rtb = RenderTargetBitmap(w, h, 96, 96, PixelFormats.Pbgra32)
                rtb.Render(root)
                enc = PngBitmapEncoder()
                enc.Frames.Add(BitmapFrame.Create(rtb))
                fs = FileStream(path, FileMode.Create)
                enc.Save(fs)
                fs.Close()
                root.Background = None
                self._open = False
                self._theme = None
            except Exception as ex:
                err.append(repr(ex))
            done.set()
        if not self._call(go):
            return 'ui not available'
        done.wait(20)
        return err[0] if err else 'ok'

    def _show_block_static(self, p):
        """The finished card with no animation and no window (used by _snapshot)."""
        shown, self._shown = self._shown, True            # don't actually Show() the window
        place, self._place_and_show = self._place_and_show, lambda: None
        try:
            return self._show_block(p, animate=False)
        finally:
            self._shown, self._place_and_show = shown, place

import cv2
import time
import asyncio
import pygame
from dataclasses import dataclass

from helpers import *
from config import save_user_config
from controller import DualSense
from connection_manager import ConnectionManager

# Colours
BG = (12, 17, 22)
PANEL = (22, 30, 38)
TOP_PANEL = (16, 79, 99)
BORDER = (55, 70, 82)
TEXT = (230, 237, 242)
MUTED = (145, 159, 170)
GOOD = (88, 214, 141)
WARN = (244, 190, 76)
BAD = (245, 91, 91)
BLUE = (101, 185, 231)

# Layout geometry
WINDOW_TITLE = "Oceanova Crawler"
WINDOW_SIZE = (1300, 720)
TOP_HEIGHT = 48
BOTTOM_HEIGHT = 105
MIN_SIDE_WIDTH = 340
SIDE_WIDTH_RATIO = 0.25
PANEL_PADDING = 15
BORDER_WIDTH = 1

VIDEO_TOOLBAR_HEIGHT = 30
VIDEO_TOOLBAR_PADDING = 5
VIDEO_BUTTON_SIZE = 20
VIDEO_BUTTON_GAP = 5
ICON_SIZE = (20, 20)

# Fonts
SMALL_FONT = None
MED_FONT = None
LARGE_FONT = None


@dataclass
class SettingsLayout:
    panel: pygame.Rect
    title: pygame.Rect
    ip_label: pygame.Rect
    ip_input: pygame.Rect
    record_dir_label: pygame.Rect
    record_dir_input: pygame.Rect
    error: pygame.Rect
    help: pygame.Rect


@dataclass
class VideoToolbarLayout:
    rect: pygame.Rect
    snapshot_button: pygame.Rect
    recording_button: pygame.Rect


@dataclass
class Layout:
    top: pygame.Rect
    video: pygame.Rect
    right: pygame.Rect
    bottom: pygame.Rect
    gear: pygame.Rect
    video_toolbar: VideoToolbarLayout


@dataclass
class SettingsState:
    open: bool = False
    active_field: str | None = None
    ip_text: str = ""
    ip_error: Optional[str] = None
    record_dir_text: str = ""
    record_dir_error: Optional[str] = None


class Column:
    def __init__(self, rect: pygame.Rect, padding: int = 16, gap: int = 8):
        self.rect = rect
        self.x = rect.left + padding
        self.y = rect.top + padding
        self.width = rect.width - padding * 2
        self.gap = gap

    def row(self, height: int) -> pygame.Rect:
        rect = pygame.Rect(self.x, self.y, self.width, height)
        self.y += height + self.gap
        return rect


def init(font_name="Segoe UI"):
    global SMALL_FONT, MED_FONT, LARGE_FONT

    SMALL_FONT = pygame.font.SysFont(font_name, 18)
    MED_FONT = pygame.font.SysFont(font_name, 22, bold=True)
    LARGE_FONT = pygame.font.SysFont(font_name, 32, bold=True)


def init_settings_layout(width: int, height: int) -> SettingsLayout:
    popup = pygame.Rect(0, 0, 520, 340)
    popup.center = (width // 2, height // 2)
    content = popup.inflate(-48, 0)

    title = pygame.Rect(content.left, popup.top + 20, content.width, 30)
    ip_label = pygame.Rect(content.left, popup.top + 68, content.width, 20)
    ip_input = pygame.Rect(content.left, popup.top + 96, content.width, 42)
    record_dir_label = pygame.Rect(content.left, popup.top + 156, content.width, 20)
    record_dir_input = pygame.Rect(content.left, popup.top + 184, content.width, 42)
    error = pygame.Rect(content.left, popup.top + 234, content.width, 20)
    help_rect = pygame.Rect(content.left, popup.bottom - 32, content.width, 20)

    return SettingsLayout(
        panel=popup,
        title=title,
        ip_label=ip_label,
        ip_input=ip_input,
        record_dir_label=record_dir_label,
        record_dir_input=record_dir_input,
        error=error,
        help=help_rect,
    )


def init_video_toolbar_layout(video_rect: pygame.Rect) -> VideoToolbarLayout:
    toolbar = pygame.Rect(
        video_rect.left, video_rect.top, video_rect.width, VIDEO_TOOLBAR_HEIGHT
    )

    snapshot_button = pygame.Rect(0, 0, VIDEO_BUTTON_SIZE, VIDEO_BUTTON_SIZE)
    snapshot_button.topleft = (
        toolbar.left + VIDEO_TOOLBAR_PADDING,
        toolbar.top + (toolbar.height - VIDEO_BUTTON_SIZE) // 2,
    )

    recording_button = pygame.Rect(0, 0, VIDEO_BUTTON_SIZE * 2, VIDEO_BUTTON_SIZE)
    recording_button.topleft = (
        snapshot_button.right + VIDEO_BUTTON_GAP,
        snapshot_button.top,
    )

    return VideoToolbarLayout(
        rect=toolbar, snapshot_button=snapshot_button, recording_button=recording_button
    )


def init_layout(width: int, height: int) -> Layout:
    side_width = max(MIN_SIDE_WIDTH, int(width * SIDE_WIDTH_RATIO))
    top = pygame.Rect(0, 0, width, TOP_HEIGHT)
    right = pygame.Rect(width - side_width, TOP_HEIGHT, side_width, height - TOP_HEIGHT)
    video = pygame.Rect(
        0, TOP_HEIGHT, width - side_width, height - TOP_HEIGHT - BOTTOM_HEIGHT
    )
    bottom = pygame.Rect(0, height - BOTTOM_HEIGHT, width - side_width, BOTTOM_HEIGHT)
    gear = pygame.Rect(top.right - 36, top.y + 8, 28, 28)
    video_toolbar = init_video_toolbar_layout(video)

    return Layout(
        top=top,
        video=video,
        right=right,
        bottom=bottom,
        gear=gear,
        video_toolbar=video_toolbar,
    )


def text(surface, font, value, xy, colour=TEXT):
    surface.blit(font.render(value, True, colour), xy)


def draw_connection_status(
    screen: pygame.Surface, rect: pygame.Rect, state: State
) -> None:
    connections = [
        ("IP LINK", state.control_connected),
        ("VIDEO", state.video_connected),
        ("CONTROLLER", state.controller_connected),
    ]

    x = rect.left

    for label, connected in connections:
        colour = GOOD if connected else BAD
        symbol = "●" if connected else "○"

        status_surface = SMALL_FONT.render(f"{label} {symbol}", True, colour)
        status_rect = status_surface.get_rect(midleft=(x, rect.centery))
        screen.blit(status_surface, status_rect)

        x = status_rect.right + 18


def draw_panel(
    screen: pygame.Surface,
    rect: pygame.Rect,
    colour: tuple[int, int, int] = PANEL,
    border_colour: tuple[int, int, int] = PANEL,
    border_width: int = BORDER_WIDTH,
) -> pygame.Rect:
    pygame.draw.rect(screen, colour, rect)
    pygame.draw.rect(screen, border_colour, rect, border_width)

    return rect.inflate(-border_width * 2, -border_width * 2)


def draw_top_panel(
    screen: pygame.Surface,
    rect: pygame.Rect,
    state: State,
    gear_rect: pygame.Rect,
    gear_icon: pygame.Surface,
) -> None:
    pygame.draw.rect(screen, TOP_PANEL, rect)
    pygame.draw.rect(screen, BORDER, rect, 1)

    title_surface = MED_FONT.render("OCEANOVA CRAWLER", True, BLUE)
    title_rect = title_surface.get_rect(
        midleft=(rect.left + PANEL_PADDING, rect.centery)
    )

    screen.blit(title_surface, title_rect)

    status_rect = pygame.Rect(
        title_rect.right + 32,
        rect.top,
        gear_rect.left - title_rect.right - 48,
        rect.height,
    )

    draw_connection_status(screen, status_rect, state)

    pygame.draw.rect(screen, TOP_PANEL, gear_rect, border_radius=5)
    pygame.draw.rect(screen, BORDER, gear_rect, width=1, border_radius=5)
    screen.blit(gear_icon, gear_icon.get_rect(center=gear_rect.center))


def draw_video_toolbar(
    screen: pygame.Surface,
    layout: VideoToolbarLayout,
    state: State,
    camera_icon: pygame.Surface,
    record_icon: pygame.Surface,
) -> None:

    # Toolbar background
    overlay = pygame.Surface(layout.rect.size, pygame.SRCALPHA)
    overlay.fill((*PANEL, 70))  # 70/255 opacity
    screen.blit(overlay, layout.rect.topleft)

    # Snapshot button
    pygame.draw.rect(screen, TEXT, layout.snapshot_button, border_radius=5)
    screen.blit(camera_icon, camera_icon.get_rect(center=layout.snapshot_button.center))

    # Recording button
    icon_center = (
        layout.recording_button.centerx - VIDEO_BUTTON_SIZE * 0.35,
        layout.recording_button.centery,
    )
    pygame.draw.rect(screen, TEXT, layout.recording_button, border_radius=5)
    screen.blit(record_icon, record_icon.get_rect(center=icon_center))

    indicator_center = (
        layout.recording_button.centerx + VIDEO_BUTTON_SIZE * 0.6,
        layout.recording_button.centery,
    )
    if state.recording:
        pygame.draw.circle(screen, (230, 50, 50), indicator_center, 4)  # Red
    else:
        pygame.draw.circle(screen, (150, 150, 150), indicator_center, 4)  # Grey


def draw_video_box(
    screen: pygame.Surface,
    rect: pygame.Rect,
    toolbar_layout: VideoToolbarLayout,
    state: State,
    camera_icon: pygame.Surface,
    record_icon: pygame.Surface,
) -> None:
    pygame.draw.rect(screen, (0, 0, 0), rect)
    pygame.draw.rect(screen, BORDER, rect, 1)

    if state.frame is None:
        wait = MED_FONT.render("WAITING FOR CRAWLER VIDEO", True, MUTED)
        screen.blit(wait, wait.get_rect(center=rect.center))
        return

    rgb = cv2.cvtColor(state.frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
    sw, sh = surf.get_size()

    scale = min((rect.width - 1) / sw, (rect.height - 1) / sh)
    scaled_size = (int(sw * scale), int(sh * scale))
    surf = pygame.transform.smoothscale(surf, scaled_size)

    screen.blit(surf, surf.get_rect(center=rect.center))

    draw_video_toolbar(screen, toolbar_layout, state, camera_icon, record_icon)


def draw_right_panel(
    screen: pygame.Surface, rect: pygame.Rect, state: State, age: float | None
) -> None:
    content = draw_panel(screen, rect)
    column = Column(content, padding=PANEL_PADDING, gap=8)

    # ARM STATE
    arm_rect = column.row(32)
    arm_label = (
        "ARMED - FULL PWM"
        if armed(state)
        else ("ARM REQUESTED" if state.arm_requested else "DISARMED")
    )
    arm_colour = WARN if armed(state) or state.arm_requested else GOOD
    arm_surface = MED_FONT.render(arm_label, True, arm_colour)

    screen.blit(arm_surface, arm_surface.get_rect(midleft=arm_rect.midleft))

    # HEADING
    heading_label_rect = column.row(20)
    text(screen, SMALL_FONT, "HEADING", heading_label_rect.topleft, MUTED)

    # YAW
    yaw_rect = column.row(48)
    yaw = state.telemetry.get("yaw")
    text(
        screen,
        LARGE_FONT,
        "---.-°" if yaw is None else f"{yaw:05.1f}°",
        yaw_rect.topleft,
    )

    # PITCH
    pitch_rect = column.row(24)
    pitch = state.telemetry.get("pitch")
    text(
        screen,
        MED_FONT,
        f"Pitch   {pitch if pitch is not None else '--'}°",
        pitch_rect.topleft,
    )

    # ROLL
    roll_rect = column.row(24)
    roll = state.telemetry.get("roll")
    text(
        screen,
        MED_FONT,
        f"Roll    {roll if roll is not None else '--'}°",
        roll_rect.topleft,
    )

    # THROTTLE
    throttle_rect = column.row(20)
    text(screen, SMALL_FONT, f"Throttle  {state.throttle:+.2f}", throttle_rect.topleft)

    # STEERING
    steering_rect = column.row(20)
    text(screen, SMALL_FONT, f"Steering  {state.steering:+.2f}", steering_rect.topleft)

    # WARNING
    warning_rect = column.row(20)
    text(
        screen, SMALL_FONT, "NO DEADMAN - ARMED STICKS LIVE", warning_rect.topleft, WARN
    )

    # MOTOR LIMIT
    motor_limit_rect = column.row(20)
    text(
        screen, SMALL_FONT, "Motor limit: 1000 / 1000", motor_limit_rect.topleft, MUTED
    )

    # MOTOR COMMANDS
    left_motor_rect = column.row(20)
    text(
        screen,
        SMALL_FONT,
        f"L command: {state.telemetry.get('left_motor', 0):+d}",
        left_motor_rect.topleft,
    )

    right_motor_rect = column.row(20)

    text(
        screen,
        SMALL_FONT,
        f"R command: {state.telemetry.get('right_motor', 0):+d}",
        right_motor_rect.topleft,
    )

    # TELEMETRY
    age_rect = column.row(20)
    age_text = "--" if age is None else f"{age:.0f} ms"

    text(screen, SMALL_FONT, f"Telemetry: {age_text}", age_rect.topleft, MUTED)

    # RTT
    rtt_rect = column.row(20)
    rtt_text = "--" if state.rtt_ms is None else f"{state.rtt_ms:.1f} ms"

    text(screen, SMALL_FONT, f"RTT: {rtt_text}", rtt_rect.topleft, MUTED)


def draw_bottom_panel(screen: pygame.Surface, rect: pygame.Rect) -> None:
    content = draw_panel(screen, rect)
    column = Column(content, padding=PANEL_PADDING, gap=8)

    options_rect = column.row(24)
    text(
        screen,
        SMALL_FONT,
        "OPTIONS = ARM   |   CIRCLE / S = STOP   |   ESC / Q = STOP + QUIT",
        options_rect.topleft,
    )

    controls_rect = column.row(24)
    text(
        screen,
        SMALL_FONT,
        "Left stick = throttle   |   Right stick = steering",
        controls_rect.topleft,
        MUTED,
    )


def draw_settings_popup(
    screen: pygame.Surface,
    layout: SettingsLayout,
    state: State,
    settings: SettingsState,
) -> None:

    # Darken background
    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))
    screen.blit(overlay, (0, 0))

    # Popup
    pygame.draw.rect(screen, PANEL, layout.panel, border_radius=8)
    pygame.draw.rect(screen, BORDER, layout.panel, width=1, border_radius=8)

    # Title
    text(screen, MED_FONT, "SETTINGS", layout.title.topleft, BLUE)

    # Ip label
    text(screen, SMALL_FONT, "IP address", layout.ip_label.topleft, MUTED)
    control_colour = GOOD if state.control_connected else BAD
    control_status = "CONNECTED" if state.control_connected else "DISCONNECTED"
    text(
        screen,
        SMALL_FONT,
        f"● {control_status}",
        (layout.ip_label.left + 150, layout.ip_label.top),
        control_colour,
    )

    # IP input
    pygame.draw.rect(screen, (20, 20, 20), layout.ip_input, border_radius=4)
    border_colour = BLUE if settings.active_field == "ip" else MUTED
    pygame.draw.rect(screen, border_colour, layout.ip_input, width=2, border_radius=4)
    ip_display = settings.ip_text
    if settings.active_field == "ip" and (pygame.time.get_ticks() // 500) % 2 == 0:
        ip_display += "|"
    text(
        screen,
        SMALL_FONT,
        ip_display,
        (layout.ip_input.left + 10, layout.ip_input.top + 12),
    )

    # Recording label
    text(
        screen,
        SMALL_FONT,
        "Recording directory",
        layout.record_dir_label.topleft,
        MUTED,
    )

    # Recording input
    pygame.draw.rect(screen, (20, 20, 20), layout.record_dir_input, border_radius=4)
    border_colour = BLUE if settings.active_field == "record_dir" else MUTED
    pygame.draw.rect(
        screen, border_colour, layout.record_dir_input, width=2, border_radius=4
    )
    record_display = settings.record_dir_text
    if (
        settings.active_field == "record_dir"
        and (pygame.time.get_ticks() // 500) % 2 == 0
    ):
        record_display += "|"
    text(
        screen,
        SMALL_FONT,
        record_display,
        (layout.record_dir_input.left + 10, layout.record_dir_input.top + 12),
    )

    # Errors
    error_text = settings.ip_error or settings.record_dir_error
    if error_text:
        text(screen, SMALL_FONT, error_text, layout.error.topleft, BAD)

    # Help
    text(
        screen,
        SMALL_FONT,
        "TAB = Next field    ENTER = Apply    ESC = Cancel",
        layout.help.topleft,
        MUTED,
    )


def close_settings(settings: SettingsState, state: State) -> None:
    settings.open = False
    settings.active_field = None
    settings.ip_text = state.pi_ip
    settings.ip_error = None
    settings.record_dir_text = str(state.record_dir)
    settings.record_dir_error = None


def open_settings(settings: SettingsState, state: State) -> None:
    settings.open = True
    settings.active_field = "ip"
    settings.ip_text = state.pi_ip
    settings.ip_error = None
    settings.record_dir_text = str(state.record_dir)
    settings.record_dir_error = None


async def save_settings(
    state: State, settings: SettingsState, connection: ConnectionManager
) -> None:
    # validate IP address
    ip = settings.ip_text.strip()
    valid, error = validate_ipv4(ip)
    if not valid:
        settings.ip_error = "Invalid IPv4 address"
        settings.record_dir_error = None
        return False

    # validate recording dir
    record_dir_text = settings.record_dir_text.strip()
    valid, error = validate_record_dir(record_dir_text)
    if not valid:
        settings.record_dir_error = error
        settings.ip_error = None
        return False

    # Apply settings to runtime state/connection
    state.record_dir = parse_record_dir(record_dir_text)
    await connection.set_pi_ip(ip)

    # Persist to disk
    if not save_user_config(state.pi_ip, state.record_dir):
        settings.record_dir_error = "Failed to save configuration"
        return False

    # Close dialog
    settings.open = False
    settings.active_field = None
    settings.ip_error = None
    settings.record_dir_error = None

    return True


async def handle_application_key(
    event: pygame.event.Event, state: State, connection: ConnectionManager
) -> None:

    if event.key in (pygame.K_ESCAPE, pygame.K_q):
        await connection.stop_motors("KEYBOARD QUIT")
        state.running = False
    elif event.key == pygame.K_s:
        await connection.stop_motors("KEYBOARD STOP")
    elif event.key == pygame.K_p:
        await connection.send({"type": "ping", "client_time": time.time()})


async def handle_settings_key(
    event: pygame.event.Event,
    state: State,
    settings: SettingsState,
    connection: ConnectionManager,
) -> None:

    if event.key == pygame.K_ESCAPE:
        close_settings(settings, state)

    elif event.key == pygame.K_RETURN:
        await save_settings(state, settings, connection)

    elif event.key == pygame.K_TAB:
        if settings.active_field == "ip":
            settings.active_field = "record_dir"
        else:
            settings.active_field = "ip"
        return

    elif event.key == pygame.K_TAB:
        if settings.active_field == "ip":
            settings.active_field = "record_dir"
        else:
            settings.active_field = "ip"

    elif event.key == pygame.K_BACKSPACE:
        if settings.active_field == "ip":
            settings.ip_text = settings.ip_text[:-1]
            settings.ip_error = None
        elif settings.active_field == "record_dir":
            settings.record_dir_text = settings.record_dir_text[:-1]
            settings.record_dir_error = None

    else:
        if not event.unicode:
            return

        if settings.active_field == "ip":
            if event.unicode in "0123456789." and len(settings.ip_text) < 15:
                settings.ip_text += event.unicode

        elif settings.active_field == "record_dir":
            settings.record_dir_text += event.unicode


async def handle_mouse_event(
    event: pygame.event.Event,
    layout: Layout,
    settings_layout: SettingsLayout,
    state: State,
    settings: SettingsState,
    connection: ConnectionManager,
) -> None:
    if event.button != 1:
        return

    if settings.open:
        if settings_layout.ip_input.collidepoint(event.pos):
            settings.active_field = "ip"
        elif settings_layout.record_dir_input.collidepoint(event.pos):
            settings.active_field = "record_dir"
        else:
            settings.active_field = None
        return

    if layout.gear.collidepoint(event.pos):
        open_settings(settings, state)
        return

    if layout.video_toolbar.snapshot_button.collidepoint(event.pos):
        await connection.take_snapshot()
        return

    if layout.video_toolbar.recording_button.collidepoint(event.pos):
        await connection.toggle_recording()
        return


async def handle_key_event(
    event: pygame.event.Event,
    state: State,
    settings: SettingsState,
    connection: ConnectionManager,
) -> None:

    if settings.open:
        await handle_settings_key(event, state, settings, connection)
    else:
        await handle_application_key(event, state, connection)


async def handle_event(
    event: pygame.event.Event,
    layout: Layout,
    settings_layout: SettingsLayout,
    state: State,
    settings: SettingsState,
    connection: ConnectionManager,
) -> None:

    if event.type == pygame.QUIT:
        await connection.stop_motors("WINDOW CLOSED")
        state.running = False
        return

    if event.type == pygame.KEYDOWN:
        await handle_key_event(event, state, settings, connection)
        return

    if event.type == pygame.MOUSEBUTTONDOWN:
        await handle_mouse_event(
            event,
            layout,
            settings_layout,
            state,
            settings,
            connection,
        )
        return


def draw_ui(
    screen: pygame.Surface,
    layout: Layout,
    settings_layout: SettingsLayout,
    state: State,
    age: float | None,
    settings: SettingsState,
    camera_icon: pygame.Surface,
    record_icon: pygame.Surface,
    gear_icon: pygame.Surface,
) -> None:
    screen.fill(BG)

    draw_top_panel(screen, layout.top, state, layout.gear, gear_icon)
    draw_video_box(
        screen, layout.video, layout.video_toolbar, state, camera_icon, record_icon
    )
    draw_right_panel(screen, layout.right, state, age)
    draw_bottom_panel(screen, layout.bottom)

    if settings.open:
        draw_settings_popup(screen, settings_layout, state, settings)


async def ui(state: State, pad: DualSense, connection: ConnectionManager) -> None:
    clock = pygame.time.Clock()
    screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)

    pygame.display.set_caption(WINDOW_TITLE)

    settings = SettingsState(ip_text=state.pi_ip)

    had_focus = True
    last_size = screen.get_size()
    layout = init_layout(*last_size)
    settings_layout = init_settings_layout(*last_size)

    gear_icon = pygame.image.load(str(resource_path("icons/gear.png"))).convert_alpha()
    gear_icon = pygame.transform.smoothscale(gear_icon, (30, 30))
    camera_icon = pygame.image.load(
        str(resource_path("icons/camera.png"))
    ).convert_alpha()
    camera_icon = pygame.transform.smoothscale(camera_icon, ICON_SIZE)
    record_icon = pygame.image.load(
        str(resource_path("icons/record.png"))
    ).convert_alpha()
    record_icon = pygame.transform.smoothscale(record_icon, ICON_SIZE)

    while state.running:

        ### --- Handle events ---
        for event in pygame.event.get():

            # check if screen size has changed and update layout accordingly
            if screen.get_size() != last_size:
                layout = init_layout(*screen.get_size())
                last_size = screen.get_size()
                settings_layout = init_settings_layout(*last_size)

            # handle mouse / key event
            await handle_event(
                event, layout, settings_layout, state, settings, connection
            )

        if not state.running:
            break

        # --- Update ---
        focused = bool(pygame.key.get_focused())
        if had_focus and not focused:
            await connection.stop_motors("WINDOW FOCUS LOST")
        had_focus = focused

        await pad.update()

        age = telemetry_age_ms(state)
        if armed(state) and age is not None and age >= TELEMETRY_OFFLINE_MS:
            await connection.stop_motors("TELEMETRY TIMEOUT")

        # --- Render ---
        draw_ui(
            screen,
            layout,
            settings_layout,
            state,
            age,
            settings,
            camera_icon,
            record_icon,
            gear_icon,
        )

        pygame.display.flip()

        clock.tick(60)

        await asyncio.sleep(0)

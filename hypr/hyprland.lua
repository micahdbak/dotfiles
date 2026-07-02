-- -----------------------------------------------------
-- Monitors & Autostart
-- -----------------------------------------------------
hl.monitor({
	output = "",
	mode = "preferred",
	position = "auto",
	scale = "auto"
})

hl.on("hyprland.start", function()
    hl.exec_cmd("hyprpaper")
    hl.exec_cmd("waybar")
end)

-- -----------------------------------------------------
-- Input & Keyboard
-- -----------------------------------------------------
hl.config({
    input = {
        kb_options = "ctrl:swap_lwin_lctl,caps:escape",

	follow_mouse = 2,
        
        touchpad = {
            natural_scroll = true
        }
    },
    
    general = {
        gaps_in = 0,
        gaps_out = 0,

        border_size = 1,

        layout = "master",

	col = {
            active_border = "#406080ff",
	    inactive_border = "#202020ff"
        }
    },
    
    decoration = {
        rounding = 0,

        blur = {
            enabled = false
        }
    },
    
    misc = {
        disable_hyprland_logo = true,
        disable_splash_rendering = true,
        force_default_wallpaper = 0
    }
})

hl.gesture({ 
    fingers = 3, 
    direction = "horizontal", 
    action = "workspace" 
})

-- -----------------------------------------------------
-- Animations
-- -----------------------------------------------------
hl.curve("fast", { type = "bezier", points = { {0.1, 0.9}, {0.1, 1.0} } })

hl.animation({ leaf = "windows",    enabled = true,  speed = 2, bezier = "fast", style = "slide" })
hl.animation({ leaf = "workspaces", enabled = true,  speed = 2, bezier = "fast", style = "slide" })
hl.animation({ leaf = "fade",       enabled = false })
hl.animation({ leaf = "border",     enabled = false })

-- -----------------------------------------------------
-- Keybindings
-- -----------------------------------------------------
local mod = "SUPER"

hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl set 5%-"))
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("brightnessctl set +5%"))

-- skip the MacBook workspace, search, mic, sleep keys

hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("playerctl previous"))
hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"))
hl.bind("XF86AudioNext", hl.dsp.exec_cmd("playerctl next"))

hl.bind("XF86AudioMute", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"))
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 1%-"))
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1.5 @DEFAULT_AUDIO_SINK@ 1%+"))

hl.bind(mod .. " + SHIFT + Return", hl.dsp.exec_cmd("kitty"))
hl.bind(mod .. " + P", hl.dsp.exec_cmd([[
bemenu-run \
    -p ">" \
    --ignorecase \
    --fixed-height \
    --border 1 \
    --border-radius 0 \
    --tb "#202020" \
    --tf "#d0d0d0" \
    --fb "#202020" \
    --ff "#ffffff" \
    --cb "#406080" \
    --cf "#ffffff" \
    --nb "#202020" \
    --nf "#c8c8c8" \
    --hb "#406080" \
    --hf "#ffffff" \
    --sb "#406080" \
    --sf "#ffffff" \
    --ab "#202020" \
    --af "#808080" \
    --scb "#202020" \
    --scf "#406080" \
    --bdr "#406080"
]]))

hl.bind(mod .. " + C", hl.dsp.window.close())
hl.bind(mod .. " + M", hl.dsp.exec_cmd("command -v hyprshutdown >/dev/null 2>&1 && hyprshutdown || hyprctl dispatch 'hl.dsp.exit()'"))

hl.bind(mod .. " + SPACE", hl.dsp.window.float({ action = "toggle" }))

hl.bind(mod .. " + Return", hl.dsp.layout("swapwithmaster"))

hl.bind(mod .. " + H", hl.dsp.layout("mfact -0.05"))
hl.bind(mod .. " + J", hl.dsp.layout("cyclenext"))
hl.bind(mod .. " + K", hl.dsp.layout("cycleprev"))
hl.bind(mod .. " + L", hl.dsp.layout("mfact +0.05"))

hl.bind(mod .. " + I", hl.dsp.layout("addmaster"))
hl.bind(mod .. " + D", hl.dsp.layout("removemaster"))

hl.bind(mod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mod .. " + SHIFT + mouse:272", hl.dsp.window.resize(), { mouse = true })

for i = 1, 9 do
    hl.bind(mod .. " + " .. i, hl.dsp.focus({ workspace = i }))
    hl.bind(mod .. " + SHIFT + " .. i, hl.dsp.window.move({ workspace = i }))
end

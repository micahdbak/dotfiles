return {
  "Mofiqul/adwaita.nvim",
  lazy = false,
  priority = 1000,
  config = function()
    vim.g.adwaita_darker = true
    vim.o.background = "dark"
    vim.cmd("colorscheme adwaita")
  end,
}

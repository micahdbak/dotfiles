return {
  "nvim-treesitter/nvim-treesitter",
  build = ":TSUpdate",
  event = { "BufReadPost", "BufNewFile" },
  config = function()
    require("nvim-treesitter").setup({})

    vim.api.nvim_create_autocmd("FileType", {
      group = vim.api.nvim_create_augroup("TreeSitterHighlight", { clear = true }),
      callback = function(event)
        pcall(vim.treesitter.start, event.buf)
      end,
    })
  end,
}

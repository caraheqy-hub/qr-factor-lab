"""Run the shared monthly cost screen for the full team/coin formula."""

from cost_screen_fangzheng_interday import run


if __name__ == '__main__':
    for window in (10, 20, 40):
        run(window=window, factor='team_coin', family='fangzheng_team_coin')

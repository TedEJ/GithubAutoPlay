# Passningsspelet (football-chess)

Passningsspelet is a top-down football puzzle game for phone and desktop. The ball starts with the player's goalkeeper at the bottom of the pitch. The player taps the teammate to pass to, and the ball travels there. The goal is to find a free route up the pitch to a teammate who can shoot and score, a bit like planning moves in chess.

This game was made outside this repository and was added unchanged in issue #51. Changes to the game come in later issues.

## Rules
- **Opposition:** the red players each have a red zone around them. A pass or shot that goes through a zone is cut out. A teammate standing inside a zone cannot be reached.
- **Failed attempt:** the pass is intercepted, the shot is blocked, or the ball reaches a player with nobody free to pass to. A ball cannot be passed back to a player who has already touched it.
- **Route:** drawn on the pitch. After a failed attempt it stays as a dashed line, so the player can learn from it.
- **Levels:** 21 fixed levels in 7 difficulty tiers, three levels per tier. The tiers need 2, 3, 3, 4, 5, 6 and 7 passes, and add more players and more defenders as they go. Levels unlock in order.
- **Stars:** up to three stars per level, depending on how few attempts were needed.
- **Hints:** three hints for the whole game. A hint shows which teammates are free to receive the ball right now.
- **Start over:** the button "Börja om" resets all levels, stars and hints.

The text in the game is in Swedish.

## How to run
Open `passningsspelet.html` in a web browser. There is nothing to install and no build step.

Stars are saved in the browser's local storage, so they stay on the same browser and device. The page loads the fonts Barlow and Barlow Condensed from Google Fonts; without a network connection the game still works with a fallback font.

## Files
- `passningsspelet.html`: the whole game in one self-contained file (HTML, CSS and JavaScript).

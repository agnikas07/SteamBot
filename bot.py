import os
import re
from dotenv import load_dotenv

load_dotenv()

import discord  # noqa: E402
from discord.ext import commands  # noqa: E402
from discord import app_commands  # noqa: E402
import random  # noqa: E402

import sheets_manager  # noqa: E402
import steam_api_manager  # noqa: E402


TOKEN = os.getenv('DISCORD_TOKEN')
STEAM_API_KEY = os.getenv('STEAM_API_KEY')
ADMIN_ID = os.getenv('ADMIN_ID')


intents = discord.Intents.default()
intents.members = True


bot = commands.Bot(command_prefix='!', intents=intents)

admin_mention = f"<@{ADMIN_ID}>"


@bot.event
async def on_ready():
    """
    Called when the bot successfully connects to Discord.
    Syncs slash commands when the bot is ready.
    """
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    print(f'Bot is in {len(bot.guilds)} guild(s):')
    for guild in bot.guilds:
        print(f'- {guild.name} (ID: {guild.id})')
    print('------')

    await bot.tree.sync()
    print("Global slash commands synced.")


@bot.event
async def on_member_join(member):
    """
    Adds a new user to the Google Sheet when they join the server.
    """
    if member.bot:
        return
    
    success, message = sheets_manager.add_new_user(member.name, member.id)

    if success:
        print(f"Successfully added {member.name} ({member.id}) to the Google Sheet: {message}")
    else:
        print(f"Failed to add {member.name} ({member.id}) to the Google Sheet: {message}")


@bot.tree.command(name="ping", description="Pings the bot to check if it's online.")
async def ping_command(interaction: discord.Interaction):
    """
    Responds to the /ping slash command.
    """
    await interaction.response.send_message("Pong!")


@bot.tree.command(name="show-sheet-members", description="Shows the data from the Google Sheet for debugging.") #this command will eventually be removed
async def show_sheet_members(interaction: discord.Interaction):
    await interaction.response.defer()

    members_data = sheets_manager.get_all_members_data()

    if not members_data:
        await interaction.followup.send("The Google Sheet is empty or could not be accessed.")
        return

    response_message = "Current members in the Google Sheet:\n"
    for member in members_data:
        username = member.get("Username", "N/A")
        discord_id = member.get("Discord ID", "N/A")
        steam_id = member.get("Steam ID", "N/A")
        response_message += f"- **{username}** (Discord ID: `{discord_id}`, Steam ID: `{steam_id}`)\n"

    if len(response_message) > 1990:
        response_message = response_message[:1990] + "...\n(Message truncated due to length limit)"

    await interaction.followup.send(response_message)


class SteamIDModal(discord.ui.Modal, title="Link Your Steam Account"):
    steam_id_input = discord.ui.TextInput(
        label="Your 17-Digit SteamID",
        placeholder="e.g., 78561398082726169",
        required=True,
        max_length=17,
        min_length=17,
        style=discord.TextStyle.short
    )

    tutorial_link = discord.ui.TextInput(
        label="How to find your SteamID (visit this link)",
        default="https://help.bethesda.net/#en/answer/49679",
        required=False,
        style=discord.TextStyle.short,
    )

    async def on_submit(self, interaction: discord.Interaction):
        entered_steam_id = self.steam_id_input.value.strip()

        if not re.fullmatch(r'7656119\d{10}', entered_steam_id):
            await interaction.response.send_message(
                "That doesn't look like a valid 17-digit SteamID. "
                "Please ensure it starts with '7656119' and is exactly 17 digits long.",
                ephemeral=True
            )
            return
        
        success, message = sheets_manager.update_user_steam_id(interaction.user.id, entered_steam_id)

        if success:
            await interaction.response.send_message(
                f"Your SteamID (`{entered_steam_id}`) has been successfully linked to this Discord server.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Failed to link your SteamID: {message}. Please try again or contact {admin_mention} for assistance.",
                ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            f"Oops! Something went wrong while submitting your SteamID: `{error}`",
            ephemeral=True
        )


@bot.tree.command(name="link-steam", description="Link your Steam account to this Discord server so you can use the other functions.")
async def link_steam(interaction: discord.Interaction):
    current_steam_id = sheets_manager.get_steam_id_for_discord_id(interaction.user.id)

    if current_steam_id:
        await interaction.response.send_message(
            f"You are already linked with SteamID `{current_steam_id}`. "
            f"If you want to change it, please contact {admin_mention}",
            ephemeral=True
        )
    else:
        await interaction.response.send_modal(SteamIDModal())


@bot.tree.command(name="letsplay", description="Finds common games among selected friends.")
@app_commands.describe(
    player2="First friend to include",
    player3="Second friend to include (optional)",
    player4="Third friend to include (optional)",
    player5="Fourth friend to include (optional)"
)
async def letsplay(interaction: discord.Interaction,
                   player2: discord.Member,
                   player3: discord.Member = None,
                   player4: discord.Member = None,
                   player5: discord.Member = None):
    await interaction.response.defer()

    players = [interaction.user, player2]
    if player3:
        players.append(player3)
    if player4:
        players.append(player4)
    if player5:
        players.append(player5)

    player_steam_ids = {}
    missing_steam_ids_names = []
    
    for player in players:
        steam_id = sheets_manager.get_steam_id_for_discord_id(player.id)
        if steam_id:
            player_steam_ids[player.id] = steam_id
        else:
            missing_steam_ids_names.append(player.name)

    if missing_steam_ids_names:
        await interaction.followup.send(
            f"Could not find Steam IDs for: {', '.join(missing_steam_ids_names)}. "
            "Please ensure their Steam IDs are entered in the Google Sheet."
        )

    all_players_game_lists = {}
    private_profiles_names = []

    for player_id, steam_id in player_steam_ids.items():
        player_member = discord.utils.get(players, id=player_id)
        player_display_name = player_member.name if player_member else f"User ID {player_id}"

        games = steam_api_manager.get_owned_games(steam_id)
        
        if games is None:
            await interaction.followup.send(
                f"Failed to fetch games for {player_display_name} (SteamID: `{steam_id}`). "
                "The Steam API might be down, or there's an issue with the key. "
                "This player will be excluded from the common games search."
            )
        elif not games:
            private_profiles_names.append(player_display_name)
        else:
            all_players_game_lists[player_id] = set(games.keys())


    if private_profiles_names:
        await interaction.followup.send(
            f"Note: Could not retrieve games for {', '.join(private_profiles_names)} "
            "because their Steam profiles are likely private or have no games. "
            "They will be excluded from the common games search."
        )

    active_players_game_lists = [game_set for game_set in all_players_game_lists.values() if game_set]

    if not active_players_game_lists:
        await interaction.followup.send(
            "No players with public Steam profiles or games found to compare."
        )
        return
    
    if len(active_players_game_lists) < 2:
        await interaction.followup.send(
            "To find common games, please ensure at least two selected players "
            "have public Steam profiles with games."
        )
        return
    
    common_game_appids = set.intersection(*active_players_game_lists)

    multiplayer_game_appids = set()
    total_common_games = len(common_game_appids)
    processed_count = 0
    message_sent = False

    if total_common_games > 5:
        await interaction.followup.send(f"Found {total_common_games} common games. Now checking for multiplayer status (this may take a moment)...")
        message_sent = True

    for appid in common_game_appids:
        if steam_api_manager.is_game_multiplayer(appid):
            multiplayer_game_appids.add(appid)
        
        processed_count += 1
        if total_common_games > 5 and processed_count % 5 == 0:
            if message_sent:
                await interaction.edit_original_response(
                    content=f"Found {total_common_games} common games. Checking for multiplayer status... ({processed_count}/{total_common_games} checked)"
                )
            else:
                await interaction.followup.send(
                    f"Found {total_common_games} common games. Checking for multiplayer status... ({processed_count}/{total_common_games} checked)"
                )
                message_sent = True

    final_common_appids = multiplayer_game_appids

    if not final_common_appids:
        await interaction.followup.send(
            "It looks like you don't have any common games among the selected players with public profiles. "
            "Perhaps try different friends or consider playing a popular multiplayer game!"
            "\n\nHere are some general suggestions for popular multiplayer games (manual suggestions for now):"
            "\n- Among Us"
            "\n- Fall Guys"
            "\n- Apex Legends"
            "\n- Valorant"
            "\n- Fortnite"
        )
    else:
        common_multiplayer_games_data = [] 
        for appid in final_common_appids:
            details = steam_api_manager.get_game_details(appid)
            if details and "name" in details and "header_image" in details:
                game_name = details["name"]
                image_url = details["header_image"]
                common_multiplayer_games_data.append({"name": game_name, "image": image_url})
            elif details and "name" in details:
                game_name = details["name"]
                common_multiplayer_games_data.append({"name": game_name, "image": None})
            else:
                common_multiplayer_games_data.append({"name": f"Unknown Game (AppID: {appid})", "image": None})

        common_multiplayer_games_data.sort(key=lambda x: x["name"])

        class PickGameView(discord.ui.View):
            def __init__(self, games_list_with_details, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.games_list_with_details = games_list_with_details
                self.re_rolls_left = 3

                self.pick_button = discord.ui.Button(label="Pick a random game for us!", style=discord.ButtonStyle.primary)
                self.add_item(self.pick_button)
                self.pick_button.callback = self.pick_first_game_button 

                self.reroll_button = discord.ui.Button(label="Re-roll game", style=discord.ButtonStyle.secondary, disabled=True)
                self.add_item(self.reroll_button)
                self.reroll_button.callback = self.reroll_game_button

            async def pick_first_game_button(self, interaction: discord.Interaction):
                if self.games_list_with_details:
                    random_game_data = random.choice(self.games_list_with_details)
                    game_name = random_game_data["name"]
                    game_image_url = random_game_data["image"]

                    embed = discord.Embed(
                        title=f"🎲 Let's play: {game_name}!",
                        color=discord.Color.blue()
                    )
                    if game_image_url:
                        embed.set_image(url=game_image_url)
                    else:
                        embed.description = "No image available for this game."

                    self.pick_button.disabled = True
                    self.reroll_button.disabled = False
                    embed.set_footer(text=f"{self.re_rolls_left} re-rolls left.")

                    await interaction.response.edit_message(
                        embed=embed,
                        view=self
                    )
                else:
                    await interaction.response.send_message("No games available to pick from.", ephemeral=True)

            async def reroll_game_button(self, interaction: discord.Interaction):
                
                if self.re_rolls_left > 0 and self.games_list_with_details:
                    self.re_rolls_left -= 1
                    random_game_data = random.choice(self.games_list_with_details)
                    game_name = random_game_data["name"]
                    game_image_url = random_game_data["image"]

                    embed = discord.Embed(
                        title=f"🎲 Re-rolled: {game_name}!",
                        color=discord.Color.green()
                    )
                    if game_image_url:
                        embed.set_image(url=game_image_url)
                    else:
                        embed.description = "No image available for this game."

                    if self.re_rolls_left == 0:
                        self.reroll_button.disabled = True
                        embed.set_footer(text="No more re-rolls left.")
                    else:
                        embed.set_footer(text=f"{self.re_rolls_left} re-rolls left.")

                    await interaction.response.edit_message(
                        embed=embed,
                        view=self
                    )
                elif self.re_rolls_left == 0:
                    await interaction.response.send_message("You have no re-rolls left for this session.", ephemeral=True)
                    self.reroll_button.disabled = True
                    await interaction.message.edit(view=self)
                else:
                    await interaction.response.send_message("No games available to re-roll from.", ephemeral=True)


            async def on_timeout(self):
                for item in self.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True
                await self.message.edit(view=self)
                print("Game picker view timed out.")


        view = PickGameView(common_multiplayer_games_data, timeout=300)

        game_names_only = [game["name"] for game in common_multiplayer_games_data]
        await interaction.followup.send(
            f"🎉 **Common MULTIPLAYER games found for {len(active_players_game_lists)} players:**\n" +
            "\n".join([f"- {name}" for name in game_names_only]),
            view=view
        )


if __name__ == "__main__":
    bot.run(TOKEN)
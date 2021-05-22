import discord, typing, asyncio, postbin, json, functools
from discord.ext import commands
from DiscordUtils.Pagination import *
from converters import *


class NoDatabaseFound(commands.CommandError):
    def __init__(self):
        super().__init__(
            "Could not find a database file! This will hopefully be accounted for in a future version, however, you currently need to create a file named `data.json` or an error will be thrown."
        )


class Tasks(commands.Cog):
    """
    All the tasks commands
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def readDB(self, ctx: commands.Context):
        try:
            file = open("data.json", "r")
        except:
            raise NoDatabaseFound()
        data: dict = (
            await self.bot.readDB()
            if hasattr(self.bot, "readDB")
            else json.loads(file.read())
        )
        tasks = data.get("tasks", {})
        return tasks.get(
            str(ctx.guild.id),
            {
                "tasks": [],
                "channel": 0,
                "roles": [],
                "messages": [],
            },
        )

    async def writeDB(self, ctx: commands.Context, data: dict):
        try:
            file = open("data.json", "r")
        except:
            raise NoDatabaseFound()
        d: dict = (
            await self.bot.readDB()
            if hasattr(self.bot, "readDB")
            else json.loads(file.read())
        )
        d.setdefault("tasks", {})
        d["tasks"][str(ctx.guild.id)] = data
        if hasattr(self.bot, "writeDB"):
            return await self.bot.writeDB(d)
        open("data.json", "r").write(json.dumps(d, indent=4, ensure_ascii=False))

    def custom_has_role_or_permission(**kwargs):
        async def check(ctx: commands.Context):
            perms = discord.Permissions()
            perms.update(**kwargs)
            if all(
                getattr(ctx.author.permissions_in(ctx.channel), perm)
                for perm, value in {k: v for k, v in dict(perms).items() if v}.items()
            ):
                return True
            data: dict = await ctx.bot.get_cog("Tasks").readDB(ctx)
            roles = data.get("roles", [])
            if any(role in [r.id for r in ctx.author.roles] for role in roles):
                return True
            if ctx.author.permissions_in(ctx.channel).manage_messages:
                return True
            raise commands.MissingAnyRole([ctx.guild.get_role(role) for role in roles])

        return commands.check(check)

    @commands.group(name="task", aliases=["tasks"], invoke_without_command=True)
    @custom_has_role_or_permission()
    async def task(
        self,
        ctx: commands.Context,
        number: typing.Union[int, None],
        user: typing.Optional[Member],
        ids: bool = False,
    ):
        """
        Views and controls tasks.
        """
        data: dict = await self.readDB(ctx)
        tasks = data["tasks"]
        channel: discord.TextChannel = self.bot.get_channel(data.get("channel"))
        if not isinstance(channel, discord.TextChannel):
            return await ctx.send(
                f"No or invalid channel set, please use `{ctx.prefix}task channel <CHANNEL>` to set one before attempting to add tasks!"
            )
        if isinstance(number, int):
            ix = int(number) - 1
            try:
                t = tasks[ix]
            except:
                return await ctx.send(f"No task with this number!")
            embed = discord.Embed(
                title=f"Task {number}", description=t["task"], color=ctx.me.color
            )
            embed.set_author(
                icon_url=ctx.guild.get_member(t["author"]).avatar_url,
                name=ctx.guild.get_member(t["author"]),
            )
            iu = ctx.guild.get_member(t["assign"][0]).avatar_url if t["assign"] else ""
            embed.set_footer(
                text=f"Assigned To: {', '.join([str(ctx.guild.get_member(m)) for m in t['assign']]) if t['assign'] else 'Unassigned'}",
                icon_url=str(iu),
            )
            return await ctx.send(embed=embed)
        pg = commands.Paginator(prefix="", suffix="")
        for i, t in enumerate(tasks):
            line = f"**{i+1}.** {t['task']}"
            if user:
                line += f" (`Author`)" if user.id == t["author"] else ""
                line += f" (`Assigned`)" if user.id in t["assign"] else ""
            if ids:
                line += f" (`{data['messages'][i]}`)" if ids else ""
            pg.add_line(line)
        if len(pg.pages) < 1:
            pg.pages.append("No tasks to do!")
        embeds = []
        color = discord.Color.random()
        for p in pg.pages:
            embed = discord.Embed(
                title=f"Tasks{f' for {user}' if user else ''}",
                color=color,
                description=p,
            )
            embeds.append(embed)
        for i, e in enumerate(embeds):
            e.set_footer(text=f"Page {i+1} of {len(embeds)}" if len(embeds) > 1 else "")
            e.add_field(
                name="Tasks Channel",
                value=f"{channel.mention} - {channel} (`{channel.id}`)\n{f'Category: {channel.category} (`{channel.category.id}`)' if channel.category else ''}",
            )
        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        epg = CustomEmbedPaginator(ctx, timeout=3600, remove_reactions=True)
        reactions = {
            "⏮️": "first",
            "◀️": "back",
            "⏹️": "delete",
            "▶️": "next",
            "⏭️": "last",
        }
        for reaction, cmd in reactions.items():
            epg.add_reaction(reaction, cmd)
        await epg.run(embeds)

    @task.command(name="search", aliases=["find"])
    @custom_has_role_or_permission()
    async def task_search(self, ctx: commands.Context, *query):
        """
        Searches for a task in the content. Will return a number and part of task content, or no results.
        """
        if not query:
            return await ctx.send(f"Please provide a search query!")
        data: dict = await self.readDB(ctx)
        embed = discord.Embed(title="Task Search Results", color=discord.Color.random())
        desc = ""
        for t in data["tasks"]:
            task = t["task"]
            if any([q.lower() in task.lower() for q in query]):
                task = f"{task[:75]}..." if len(task) > 75 else task
                desc += f"\n**{data['tasks'].index(t)+1}.** {task}"
                continue
        embed.description = (
            desc
            if desc
            else f"Your search for '{' '.join(query)}' returned no results."
        )
        embed.set_footer(
            text=f"Search Query: {' '.join(query)}", icon_url=ctx.author.avatar_url
        )
        await ctx.send(embed=embed)

    @task.command(name="channel", aliases=["chan"])
    @custom_has_role_or_permission()
    async def task_channel(self, ctx: commands.Context, channel: TextChannel = None):
        """
        Sets the tasks channel.
        """
        data: dict = await self.readDB(ctx)
        if not channel:
            data["channel"] = 0
            await ctx.send("Removed the tasks channel!")
            return await self.writeDB(ctx, data)
        data["channel"] = channel.id
        await ctx.send(f"Set the tasks channel to {channel.mention}!")
        if ctx.me.permissions_in(channel).manage_channels:
            await channel.edit(
                topic=f"Don't send or delete messages in this channel!\nThis channel is for keeping track of tasks, and is managed by {ctx.me.mention}."
            )
        await self.writeDB(ctx, data)

    #    @task.command(name="permission", aliases=['permissions', 'perm', 'perms'])
    #    async def task_permissions(
    #        self, ctx: commands.Context, perm):
    #        """
    #        Sets the tasks management permission.
    #        """
    #        data: dict = await self.readDB(ctx)
    #        if role == "remove":
    #            data["role"] = 0
    #            await ctx.send("Removed the tasks management role!")
    #        elif isinstance(role, discord.Role):
    #            data["role"] = role.id
    #            await ctx.send(f"Set the tasks management role to {role.mention}!")
    #        else:
    #            raise commands.BadArgument(f'Role "{role}" not found.')
    #        await self.writeDB(ctx, data)

    @task.group(name="role")
    @custom_has_role_or_permission()
    async def task_role(self, ctx: commands.Context):
        """
        Shows roles currently whitelisted to use tasks commands.
        """
        data: dict = await self.readDB(ctx)
        roles = data.get("roles", [])
        embed = discord.Embed(
            title="Task Roles",
            description=f"{' '.join([r.mention for r in [ctx.guild.get_role(ro) for ro in roles]])}",
            color=ctx.me.color,
        )
        await ctx.send(embed=embed)

    @task_role.command(name="add")
    @custom_has_role_or_permission()
    async def task_role_add(self, ctx: commands.Context, *roles: Role):
        """
        Adds roles to the list of roles allowed to use tasks commmands.
        """
        data: dict = await self.readDB(ctx)
        roledata = data.get("roles", [])
        alr = []
        for r in roles:
            if r in roledata:
                roledata.append(r.id)
            else:
                alr.append(r)
        embed = discord.Embed(
            title="Roles Added",
            description=f"{' '.join([r.mention for r in roles if r not in alr]) or 'None added!'}",
            color=ctx.me.color,
        )
        if alr:
            embed.add_field(
                name="Already Added", value=f"{' '.join([r.mention for r in alr])}"
            )
        await ctx.send(embed=embed)
        data["roles"] = roledata
        await self.writeDB(ctx, data)

    @task_role.command(name="remove")
    @custom_has_role_or_permission()
    async def task_role_remove(self, ctx: commands.Context, *roles: Role):
        """
        Removes roles from the list of roles allowed to use tasks commmands.
        """
        data: dict = await self.readDB(ctx)
        roledata = data.get("roles", [])
        notin = []
        for r in roles:
            if r in roledata:
                roledata.remove(r.id)
            else:
                notin.append(r)
        embed = discord.Embed(
            title="Roles Removed",
            description=f"{' '.join([r.mention for r in roles if r not in notin])}",
            color=ctx.me.color,
        )
        if notin:
            embed.add_field(
                name="Not Added", value=f"{' '.join([r.mention for r in notin])}"
            )
        await ctx.send(embed=embed)
        data["roles"] = roledata
        await self.writeDB(ctx, data)

    @task.command(name="add", aliases=["create", "new", "+"])
    @custom_has_role_or_permission()
    async def task_add(
        self, ctx: commands.Context, assign: typing.Optional[discord.Member], *, task
    ):
        """
        Adds a new task to the list.
        """
        data: dict = await self.readDB(ctx)
        c: discord.TextChannel = ctx.guild.get_channel(data.get("channel"))
        if not isinstance(c, discord.TextChannel):
            return await ctx.send(f"No valid task channel set!")
        m = await c.send(f"New Task...")
        data["tasks"].append(
            {
                "task": task,
                "author": ctx.author.id,
                "assign": [assign.id] if assign and not assign.bot else [],
            }
        )
        data["messages"].append(m.id)
        await self.writeDB(ctx, data)
        await ctx.reply(
            f"Added your task to the list{f' and assigned it to `{assign}`' if assign and not assign.bot else ''}!\nNumber: {len(data['tasks'])}"
        )
        await self.task_fix(ctx, start=len(data["tasks"]), end=len(data["tasks"]))

    @task.command(name="assign")
    @custom_has_role_or_permission()
    async def task_assign(self, ctx: commands.Context, task: int, *users: Member):
        """
        Assigns a task to a user.
        """
        data: dict = await self.readDB(ctx)
        users = [user for user in users if not user.bot]
        if len(users) < 1:
            return await ctx.send("You can't assign tasks to bots!")
        users = [
            user for user in users if getattr(user.guild_permissions, "manage_messages")
        ]
        if len(users) < 1:
            return await ctx.send(
                "You can only assign tasks to people with the `Manage Messages` permission!"
            )
        try:
            c: discord.TextChannel = self.bot.get_channel(data["channel"])
        except:
            return await ctx.send(f"No valid task channel set!")
        task = task - 1
        try:
            t = data["tasks"][task]
        except:
            return await ctx.send(f"There is no task with the number `{task}`!")
        if ctx.author.id in [642416218967375882, t["author"]]:
            if len(users) > 0:
                rm = []
                add = []
                for user in users:
                    if user.id in t["assign"]:
                        t["assign"].remove(user.id)
                        rm.append(str(user))
                    else:
                        t["assign"].append(user.id)
                        add.append(str(user))
                data["tasks"][task] = t
                n = "\n"
                await ctx.send(
                    f"Updated task `{task+1}`'s assignments!{f'{n}Added: '+', '.join(add) if add else ''}{f'{n}Removed: '+', '.join(rm) if rm else ''}"
                )
            else:
                if t["assign"] == []:
                    return await ctx.send(f"This task is not assigned to anybody!")
                t["assign"] = []
        else:
            return await ctx.send(
                f"Only the author of this task can change who it's assigned to! (The author is {ctx.guild.get_member(t['author'])})"
            )
        await self.writeDB(ctx, data)
        await self.task_fix(ctx, start=task, end=task + 1)

    @task.command(name="author")
    @custom_has_role_or_permission()
    async def task_author(self, ctx: commands.Context, task: int, author: Member):
        """
        Sets another member as the author of a task, giving them full control over said task.
        """
        data = await self.readDB(ctx)
        try:
            t = data["tasks"][task - 1]
        except:
            return await ctx.send(f"Task `{task}` doesn't exist!")
        if t["author"] != ctx.author.id:
            return await ctx.send(
                f"You did not write this task, so you cannot transfer ownership!"
            )
        data["tasks"][task - 1]["author"] = author.id
        await ctx.send(f"Changed task `{task}`'s author to {author}!")
        await self.writeDB(ctx, data)
        await self.task_fix(ctx, start=task, end=task + 1)

    @task.command(name="claim")
    @custom_has_role_or_permission()
    async def task_claim(self, ctx: commands.Context, *tasks: int):
        """
        Claims a task if it's not assigned to somebody else already.
        """
        data: dict = await self.readDB(ctx)
        try:
            c: discord.TextChannel = self.bot.get_channel(data["channel"])
        except:
            return await ctx.send(f"No valid task channel set!")
        tasks = [t for t in sorted(tasks) if t <= len(data["tasks"])]
        for task in sorted(tasks):
            try:
                t = data["tasks"][task - 1]
            except:
                await ctx.send(f"No task with the number `{task}`!")
                continue
            if t["assign"] == [] or t["author"] == ctx.author.id:
                t["assign"].append(ctx.author.id)
                await ctx.send(f"Assigned `{t['task']}` to you!", no_edit=True)
            else:
                await ctx.send(
                    f"Task `{task}` is already assigned to somebody else and you are not the author!",
                    no_edit=True,
                )
            data["tasks"][task - 1] = t
        await self.writeDB(ctx, data)
        await self.task_fix(
            ctx, start=sorted(tasks)[0] - 1, end=sorted(tasks)[len(tasks) - 1]
        )

    @task.command(name="edit")
    @custom_has_role_or_permission()
    async def task_edit(self, ctx: commands.Context, task: int, *, new):
        """
        Edits a task that you authored.
        """
        data: dict = await self.readDB(ctx)
        try:
            c: discord.TextChannel = self.bot.get_channel(data["channel"])
        except:
            return await ctx.send(f"No valid task channel set!")
        try:
            t = data["tasks"][int(task) - 1]
        except:
            return await ctx.send(f"There is no task with the number `{task}`!")
        if t["author"] != ctx.author.id:
            return await ctx.send(
                f"Only the author of this task can edit it!\nThe author is {ctx.guild.get_member(t['author'])}"
            )
        old = t["task"]
        t["task"] = new
        send = f"Changed task `{task}`!\n**Before:** ```\n{old}```\n**After:** ```\n{new}```"
        send = (
            send
            if len(send) < 2000
            else f"Changed task `{task}`!\n**Before:** ```\n{await postbin.postAsync(old)}```\n**After:** ```\n{await postbin.postAsync(new)}"
        )
        await ctx.send(send)
        data["tasks"][int(task) - 1] = t
        await self.writeDB(ctx, data)
        await self.task_fix(ctx, start=task - 1, end=task)

    @task.command(name="append")
    @custom_has_role_or_permission()
    async def task_append(self, ctx: commands.Context, task: int, *, new):
        """
        Appends given arguments to an existing task.
        """
        data: dict = await self.readDB(ctx)
        try:
            t = data["tasks"][task - 1]
        except:
            return await ctx.send(f"No task with the number `{task}`!")
        if t["author"] != ctx.author.id:
            return await ctx.send(
                f"Only the author of this task can append to it!\nThe author is {ctx.guild.get_member(t['author'])}"
            )
        old = t["task"]
        t["task"] += f"\n{new}"
        data["tasks"][task - 1] = t
        await ctx.send(
            f"Added to task `{task}`!\n**Before:** ```\n{old}```\n**After:** ```\n{t['task']}```"
        )
        await self.writeDB(ctx, data)
        await self.task_fix(ctx, start=task - 1, end=task)

    @task.command(name="remove", aliases=["delete", "rm", "-"])
    @custom_has_role_or_permission()
    async def task_remove(self, ctx: commands.Context, *tasks: int):
        """
        Removes a task from the list by index (you can only remove your own tasks or ones that are assigned to you).
        """
        if not tasks:
            return await ctx.send(f"Please provide at least one task to delete!")
        data: dict = await self.readDB(ctx)
        try:
            c: discord.TextChannel = self.bot.get_channel(data["channel"])
        except:
            return await ctx.send(f"No valid task channel set!")
        tasks = list(set(tasks))
        success = []
        fail = []
        notauth = []
        for task in sorted(tasks, reverse=True):
            i = int(task) - 1
            try:
                t = data["tasks"][i]
            except:
                fail.append(f"`{task}`")
                continue
            allowed: list = [642416218967375882, t["author"]]
            allowed.extend(t["assign"])
            if ctx.author.id in allowed:
                data["tasks"].remove(t)
                m = data["messages"][i]
                data["messages"].remove(m)
                success.append(f"`{t['task']}` (`{task}`)")
                try:
                    await (await c.fetch_message(m)).delete()
                except:
                    pass
            #                        f"Looks like the message tied to this task was deleted! No worries, the database is correct and your task has been removed, but make sure task messages aren't deleted in the future!",
            else:
                notauth.append(f"`{t['task']}` (`{task}`)")
        #                    f"`{t['task']}` is not written by or assigned to you so you can't remove it!",
        n = "\n"
        summary = f"{(f'**Tasks Deleted:** '+ n.join(reversed(success))) if success else ''}{(f'{n}**Not Found:** '+', '.join(reversed(fail))) if fail else ''}{(f'{n}**Not Author/Assigned:** '+', '.join(reversed(notauth))) if notauth else ''}"
        if len(summary) > 2000:
            summary = f"The summary of deleted tasks was too long, find it at {await postbin.postAsync(summary)}"
        await ctx.send(summary)
        await self.writeDB(ctx, data)
        await self.task_fix(ctx, start=sorted(tasks)[0])

    @task.command(name="move", aliases=["mv", "prioritize"])
    @custom_has_role_or_permission()
    async def task_move(self, ctx: commands.Context, task: int, new_priority: int):
        """
        Moves a task, effectively changing the priority by shifting it up or down in the list.
        """
        data: dict = await self.readDB(ctx)
        try:
            t: dict = data["tasks"].pop(task - 1)
        except:
            return await ctx.send(f"No task with the number `{task}`!")
        data["tasks"].insert(new_priority - 1, t)
        await self.writeDB(ctx, data)
        s = task if task < new_priority else new_priority
        e = task if task > new_priority else new_priority
        await ctx.send(f"Moved task `{task}` to position `{new_priority}`!")
        await self.task_fix(ctx, start=s, end=e)

    async def task_fix(self, ctx: commands.Context, start: int = 0, end: int = 1000):
        async with ctx.typing():
            data: dict = await self.readDB(ctx)
            failed = []
            try:
                c: discord.TextChannel = self.bot.get_channel(data["channel"])
            except:
                return await ctx.send(f"No valid task channel set!")
            start = start - 1 if start > 0 else 0
            for t in data["tasks"][start:end]:
                i = data["tasks"].index(t)
                embed = discord.Embed(
                    title=f"Task {i+1}",
                    description=t["task"],
                    color=ctx.me.color,
                )
                embed.set_author(
                    icon_url=ctx.guild.get_member(t["author"]).avatar_url,
                    name=ctx.guild.get_member(t["author"]),
                )
                iu = (
                    ctx.guild.get_member(t["assign"][0]).avatar_url
                    if t["assign"]
                    else ""
                )
                embed.set_footer(
                    text=f"Assigned To: {', '.join([str(ctx.guild.get_member(m)) for m in t['assign']]) if t['assign'] else 'Unassigned'}",
                    icon_url=str(iu),
                )
                try:
                    await (await c.fetch_message(data["messages"][i])).edit(
                        content=None, embed=embed
                    )
                except:
                    failed.append(f"{i+1} : `{data['messages'][i]}`")
            await c.purge(limit=None, check=lambda m: m.id not in data["messages"])
            return failed

    @task.command(name="fix")
    @custom_has_role_or_permission(administrator=True)
    async def task_fix_cmd(self, ctx: commands.Context, start: int = 0):
        """
        Edits all messages in the tasks channel (start and downwards if start is provided), fixing the format.
        """
        n = "\n"
        failed = await self.task_fix(ctx, start=start)
        await ctx.send(
            f"Done fixing tasks!{(f'{n}Tasks missing messages:{n}'+', '.join(failed)) if failed else ''}",
            delete_after=10,
        )

    @task.command(name="forcefix")
    @custom_has_role_or_permission(administrator=True)
    async def task_forcefix(self, ctx: commands.Context):
        """
        Task fix, but it wipes the channel and resets the messages just to make sure there aren't any booboos.
        """
        data: dict = await self.readDB(ctx)
        try:
            c: discord.TextChannel = self.bot.get_channel(data["channel"])
        except:
            return await ctx.send(f"No valid task channel set!")
        conf = await ctx.send(
            f"Are you sure you want to reset the tasks channel (does not delete tasks)?"
        )
        await conf.add_reaction("✅")
        await conf.add_reaction("❌")
        try:
            reaction, member = await self.bot.wait_for(
                "reaction_add",
                check=lambda reaction, member: str(reaction.emoji) in ["✅", "❌"]
                and member.id == ctx.author.id
                and reaction.message.id == conf.id,
                timeout=60,
            )
            if reaction.emoji == "✅":
                async with ctx.typing():
                    await c.purge(limit=None)
                    data["messages"] = []
                    for task in data["tasks"]:
                        m = await c.send(task["task"])
                        data["messages"].append(m.id)
                    await self.writeDB(ctx, data)
                    await self.task_fix(ctx)
                if c.id != ctx.channel.id:
                    await ctx.send("Done!")
            else:
                try:
                    await conf.edit(f"Cancelled forcefix", delete_after=3)
                except:
                    pass
        except asyncio.TimeoutError:
            return await ctx.send(
                f"Timeout!\n{ctx.author.mention}, you failed to confirm in the allotted time! You can run the command again if you still need to reset.",
                delete_after=5,
            )
        finally:
            try:
                await conf.delete()
            except:
                return

    @task.command(name="wipe", aliases=["clear"], enabled=False)
    @commands.has_permissions(administrator=True)
    async def task_wipe(self, ctx: commands.Context):
        """
        DELETES ALL TASKS FROM THE SERVER!!! Use with caution.
        """
        check: discord.Message = await ctx.send(
            f"Are you sure you want to delete **__ALL__** tasks from {ctx.guild}?"
        )
        for r in ["✅", "❌"]:
            await check.add_reaction(r)

        def checkfunc(reaction: discord.Reaction, user: discord.Member):
            return (
                reaction.emoji in ["✅", "❌"]
                and reaction.message.channel.id == ctx.channel.id
                and user.id == ctx.author.id
            )

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add", check=checkfunc, timeout=60
            )
        except:
            return await ctx.send(f"Timeout, cancelled task wipe", delete_after=3)
        if reaction.emoji == "❌":
            return await ctx.send("Cancelled task wipe")
        await check.remove_reaction("✅", ctx.author)
        if reaction.emoji == "❌":
            return await ctx.send("Cancelled task wipe", delete_after=3)
        try:
            await check.edit(content=check.content.replace("sure", "*really* sure"))
            reaction, user = await self.bot.wait_for(
                "reaction_add", check=check, timeout=60
            )
        except:
            return await ctx.send(f"Timeout, cancelled task wipe", delete_after=3)
        await ctx.send(f"There's no going back now... Wiping tasks!")
        data = await self.readDB(ctx)
        data["messages"] = []
        data["tasks"] = []
        await self.writeDB(ctx, data)
        await self.task_fix(ctx)
        await ctx.send(
            f"Done wiping tasks! The tasks channel is now a clean slate.",
            delete_after=3,
        )


def setup(bot: commands.Bot):
    bot.add_cog(Tasks(bot))

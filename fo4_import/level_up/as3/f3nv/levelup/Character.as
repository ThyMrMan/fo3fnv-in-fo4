package f3nv.levelup
{
   import f3ui.Text;

   // What the level-up menu knows of the player: the listed perks (name, description, image, level, ranks, ranks
   // held), the skills (name, description, image, tagged, points set but not spent), the values the requirement rows
   // test (SPECIAL then skills), and those rows. It answers which perks can be taken now, which the points set
   // would open, and each requirement as the menu shows it.
   // See docs/fork/fo4_level_up_plan.md#menu
   public class Character
   {
      // Between a table's entries (F3NV_LevelUp.psc's SEP).
      public static const SEP:String = "\t";
      // Requirement kinds and comparisons (fo4_import/spike/level_up.py).
      public static const VALUE:int = 0;
      public static const SEX:int = 1;
      public static const PERK:int = 2;
      public static const LEVEL:int = 3;
      // A perk another mod added (F3NV_LevelUp.AddPerk): the game's own test of its conditions, met when unlisted.
      public static const GAME:int = 4;
      private static const OPS:Array = ["=", "!=", ">", "", "<", "<="];

      // Open's modes (F3NV_LevelUp.psc): a level-up, the tag skill menu, the trait menu.
      public static const LEVEL_UP:int = 0;
      public static const TAGS:int = 1;
      public static const TRAITS:int = 2;
      // A skill's tag: none, SetPlayerTagSkill's suggestion (the tag menu may change it), tagged.
      public static const SUGGESTED:int = 1;
      public static const TAGGED:int = 2;

      public var mode:int;
      // How many tags in all (TAGS) or traits at most (TRAITS); each new tag's bonus.
      public var wanted:int;
      public var bonus:int;
      public var perks:Array = [];
      public var skills:Array = [];
      // {name, text, image, held, picked}
      public var traits:Array = [];
      public var values:Array = [];
      public var rows:Array = [];
      public var level:int;
      public var sex:int;
      public var cap:int;
      public var specials:int;
      public var perkPoints:int;
      public var skillPoints:int;
      // Whether the perk page opens showing every perk (the MCM option).
      public var showAll:Boolean;

      // F3NV_LevelUp.psc's Built, in its order: points, level, sex, cap; the perk tables and ranks held; the skill
      // tables, values and tags; how many values are SPECIAL; the requirement rows' columns; the mode, the count
      // and bonus; the trait tables and traits held; whether to show every perk at first; each table's perk and
      // row counts.
      public function Character(args:Array)
      {
         perkPoints = int(args[0]);
         skillPoints = int(args[1]);
         level = int(args[2]);
         sex = int(args[3]);
         cap = int(args[4]);
         var names:Array = split(args[5]), texts:Array = split(args[6]), images:Array = split(args[7]);
         var levels:Array = split(args[8]), ranks:Array = split(args[9]), held:Array = split(args[10]);
         for (var i:int = 0; i < names.length; i++)
         {
            perks.push({name: names[i], text: texts[i] || "", image: images[i] || "", level: int(levels[i]),
                        ranks: Math.max(1, int(ranks[i])), held: int(held[i]), rows: []});
         }
         names = split(args[11]);
         texts = split(args[12]);
         images = split(args[13]);
         values = numbers(split(args[14]));
         var tags:Array = split(args[15]);
         specials = int(args[16]);
         for (i = 0; i < names.length; i++)
         {
            var tag:int = int(tags[specials + i]);
            skills.push({name: names[i], text: texts[i] || "", image: images[i] || "", tag: tag, tagged: tag > 0,
                         pending: 0});
         }
         readRows(args.slice(17, 25), split(args[33]), split(args[34]));
         mode = int(args[25]);
         wanted = int(args[26]);
         bonus = int(args[27]);
         names = split(args[28]);
         texts = split(args[29]);
         images = split(args[30]);
         held = split(args[31]);
         for (i = 0; i < names.length; i++)
         {
            traits.push({name: names[i], text: texts[i] || "", image: images[i] || "", held: held[i] == "1",
                         picked: held[i] == "1"});
         }
         showAll = Boolean(args[32]);
      }

      // How many skills are tagged now (in the tag menu, as the player has them set).
      public function tagCount() : int
      {
         var out:int = 0;
         for each (var skill:Object in skills)
         {
            out += skill.tagged ? 1 : 0;
         }
         return out;
      }

      // Tag or untag skill `index` in the tag menu: a skill tagged before (not a suggestion) stays, and no more than
      // `wanted` are tagged; whether it changed.
      public function toggleTag(index:int) : Boolean
      {
         var skill:Object = skills[index];
         if (skill.tag == TAGGED || !skill.tagged && tagCount() >= wanted)
         {
            return false;
         }
         skill.tagged = !skill.tagged;
         return true;
      }

      // How many traits are picked.
      public function traitCount() : int
      {
         var out:int = 0;
         for each (var trait:Object in traits)
         {
            out += trait.picked ? 1 : 0;
         }
         return out;
      }

      // Pick or drop trait `index`, no more than `wanted` picked; whether it changed.
      public function toggleTrait(index:int) : Boolean
      {
         var trait:Object = traits[index];
         if (!trait.picked && traitCount() >= wanted)
         {
            return false;
         }
         trait.picked = !trait.picked;
         return true;
      }

      // `items`' entries with `key` set, as one int, bit i for entry i (the tag and trait menus' answer).
      public static function mask(items:Array, key:String) : int
      {
         var out:int = 0;
         for (var i:int = 0; i < items.length && i < 31; i++)
         {
            out |= items[i][key] ? 1 << i : 0;
         }
         return out;
      }

      // `text`'s entries; none for "".
      public static function split(text:Object) : Array
      {
         return text == null || String(text) == "" ? [] : String(text).split(SEP);
      }

      private static function numbers(texts:Array) : Array
      {
         var out:Array = [];
         for each (var text:String in texts)
         {
            out.push(Number(text));
         }
         return out;
      }

      // The rows' columns (owner, kind, target, comparison, value, or-next, label, then the indexes of the rows whose
      // perk test, or the game's own test, passes), each row added to its perk's. Each table's (group's) rows count
      // their owners, and their perk targets, from 0: they move to where the group's perks start, by `perkCounts` and
      // `rowCounts`, one per group.
      private function readRows(columns:Array, perkCounts:Array, rowCounts:Array) : void
      {
         var owners:Array = split(columns[0]), kinds:Array = split(columns[1]), targets:Array = split(columns[2]);
         var compares:Array = split(columns[3]), needs:Array = split(columns[4]), ors:Array = split(columns[5]);
         var labels:Array = split(columns[6]), held:Object = {};
         for each (var at:String in split(columns[7]))
         {
            held[int(at)] = true;
         }
         var moves:Array = groupStarts(perkCounts, rowCounts);
         for (var i:int = 0; i < owners.length; i++)
         {
            var by:int = i < moves.length ? moves[i] : 0;
            var kind:int = int(kinds[i]), target:int = int(targets[i]), owner:int = int(owners[i]);
            var row:Object = {kind: kind, target: kind == PERK && target >= 0 ? target + by : target,
                              compare: int(compares[i]), need: Number(needs[i]), or: ors[i] == "1",
                              label: labels[i] || "", unlisted: held[i] == true};
            rows.push(row);
            owner = owner >= 0 ? owner + by : owner;
            if (owner >= 0 && owner < perks.length)
            {
               perks[owner].rows.push(row);
            }
         }
      }

      // Per row, where its group's perks start among every group's: group g has rowCounts[g] rows and perkCounts[g]
      // perks, in order.
      public static function groupStarts(perkCounts:Array, rowCounts:Array) : Array
      {
         var out:Array = [];
         var first:int = 0;
         for (var g:int = 0; g < rowCounts.length; g++)
         {
            for (var r:int = 0; r < int(rowCounts[g]); r++)
            {
               out.push(first);
            }
            first += int(perkCounts[g]);
         }
         return out;
      }

      // Skill `index`'s base value, and with the points set on it.
      public function skillValue(index:int, pending:Boolean = false) : Number
      {
         return values[specials + index] + (pending ? skills[index].pending : 0);
      }

      // The points set on skills and not yet spent.
      public function pendingPoints() : int
      {
         var out:int = 0;
         for each (var skill:Object in skills)
         {
            out += skill.pending;
         }
         return out;
      }

      // Set `by` more (or fewer) points on skill `index`, within the points left, its base and the cap; whether it
      // changed.
      public function setPoints(index:int, by:int) : Boolean
      {
         var skill:Object = skills[index];
         var next:int = Math.max(0, Math.min(skill.pending + by, skillPoints - pendingPoints() + skill.pending,
                                             cap - skillValue(index)));
         var changed:Boolean = next != skill.pending;
         skill.pending = next;
         return changed;
      }

      // The value `row` tests, with the points set on skills when `pending`.
      public function have(row:Object, pending:Boolean = false) : Number
      {
         if (row.kind == VALUE)
         {
            var skill:int = row.target - specials;
            var extra:Number = pending && skill >= 0 && skill < skills.length ? skills[skill].pending : 0;
            return row.target >= 0 ? values[row.target] + extra : 0;
         }
         if (row.kind == SEX)
         {
            return sex;
         }
         if (row.kind == PERK)
         {
            return row.target >= 0 ? (perks[row.target].held > 0 ? 1 : 0) : (row.unlisted ? 1 : 0);
         }
         if (row.kind == GAME)
         {
            return row.unlisted ? 1 : 0;
         }
         return level;
      }

      public function met(row:Object, pending:Boolean = false) : Boolean
      {
         var value:Number = have(row, pending);
         switch (row.compare)
         {
            case 0: return value == row.need;
            case 1: return value != row.need;
            case 2: return value > row.need;
            case 3: return value >= row.need;
            case 4: return value < row.need;
         }
         return value <= row.need;
      }

      // Whether perk `index` has a rank left and the player meets its level and every requirement group (rows
      // OR'd with the next form a group that needs one of them), with the points set when `pending`.
      public function eligible(index:int, pending:Boolean = false) : Boolean
      {
         var perk:Object = perks[index];
         if (perk.held >= perk.ranks || level < perk.level)
         {
            return false;
         }
         var group:Boolean = false;
         for each (var row:Object in perk.rows)
         {
            group = group || met(row, pending);
            if (!row.or)
            {
               if (!group)
               {
                  return false;
               }
               group = false;
            }
         }
         return true;
      }

      // The perks the points set on skills would make eligible, by name.
      public function unlocked() : Array
      {
         var out:Array = [];
         for (var i:int = 0; i < perks.length; i++)
         {
            if (eligible(i, true) && !eligible(i))
            {
               out.push(perks[i].name);
            }
         }
         return out;
      }

      // Perk `index`'s requirements as shown, one line per group ("Science 50 or Guns 50"), each unmet one with the
      // player's value ("Science 50 (you have 45)"); the level first. [text, met] each.
      public function requirements(index:int) : Array
      {
         var perk:Object = perks[index];
         var out:Array = [[Text.fill("$F3NV_LU_LEVEL\t" + perk.level), level >= perk.level]];
         var parts:Array = [];
         var good:Boolean = false;
         for each (var row:Object in perk.rows)
         {
            var ok:Boolean = met(row);
            good = good || ok;
            parts.push(ok || row.kind == SEX || row.kind == PERK || row.kind == GAME ? shown(row)
                       : Text.fill("$F3NV_LU_YOU_HAVE\t" + shown(row) + "\t" + Math.floor(have(row))));
            if (!row.or)
            {
               out.push([parts.join(" " + Text.translate("$F3NV_LU_OR") + " "), good]);
               parts = [];
               good = false;
            }
         }
         return out;
      }

      // `row` as shown: "Science 50", "Strength < 5", "Level 8", the sex, the perk's name, or the perk's own conditions.
      private function shown(row:Object) : String
      {
         if (row.kind == GAME)
         {
            return Text.translate("$F3NV_LU_OWN_TEST");
         }
         if (row.kind == SEX)
         {
            var female:Boolean = (row.need == 1) == (row.compare == 0);
            return Text.translate(female ? "$F3NV_LU_FEMALE" : "$F3NV_LU_MALE");
         }
         if (row.kind == LEVEL)
         {
            return Text.fill("$F3NV_LU_LEVEL\t" + (OPS[row.compare] ? OPS[row.compare] + " " : "") + row.need);
         }
         if (row.kind == PERK)
         {
            return (row.need == 0) == (row.compare == 0) ? Text.fill("$F3NV_LU_NOT\t" + row.label) : row.label;
         }
         return row.label + " " + (OPS[row.compare] ? OPS[row.compare] + " " : "") + row.need;
      }
   }
}

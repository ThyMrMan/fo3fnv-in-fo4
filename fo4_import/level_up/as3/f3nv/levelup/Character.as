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
      private static const OPS:Array = ["=", "!=", ">", "", "<", "<="];

      public var perks:Array = [];
      public var skills:Array = [];
      public var values:Array = [];
      public var rows:Array = [];
      public var level:int;
      public var sex:int;
      public var cap:int;
      public var specials:int;
      public var perkPoints:int;
      public var skillPoints:int;

      // F3NV_LevelUp.psc's Send, in its order: points, level, sex, cap; the perk tables and ranks held; the skill
      // tables, values and tags; how many values are SPECIAL; the requirement rows' columns.
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
            skills.push({name: names[i], text: texts[i] || "", image: images[i] || "",
                         tagged: tags[specials + i] == "1", pending: 0});
         }
         readRows(args.slice(17));
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

      // The rows' columns (owner, kind, target, comparison, value, or-next, label, unlisted perk held), each row
      // added to its perk's.
      private function readRows(columns:Array) : void
      {
         var owners:Array = split(columns[0]), kinds:Array = split(columns[1]), targets:Array = split(columns[2]);
         var compares:Array = split(columns[3]), needs:Array = split(columns[4]), ors:Array = split(columns[5]);
         var labels:Array = split(columns[6]), unlisted:Array = split(columns[7]);
         for (var i:int = 0; i < owners.length; i++)
         {
            var row:Object = {kind: int(kinds[i]), target: int(targets[i]), compare: int(compares[i]),
                              need: Number(needs[i]), or: ors[i] == "1", label: labels[i] || "",
                              unlisted: unlisted[i] == "1"};
            rows.push(row);
            var owner:int = int(owners[i]);
            if (owner >= 0 && owner < perks.length)
            {
               perks[owner].rows.push(row);
            }
         }
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
            parts.push(ok || row.kind == SEX || row.kind == PERK ? shown(row)
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

      // `row` as shown: "Science 50", "Strength < 5", "Level 8", the sex, or the perk's name.
      private function shown(row:Object) : String
      {
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

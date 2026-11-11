package
{
   import flash.display.MovieClip;

   // The dialogue movie's root: the game drives its dialogue menu at root.Menu_mc, as in its own movie.
   // See docs/fork/fo4_dialogue_menu_plan.md#own-movie
   public class DialogueMenuRoot extends MovieClip
   {
      public var Menu_mc:DialogueMenu;

      public function DialogueMenuRoot()
      {
         super();
         this.Menu_mc = new DialogueMenu();
         addChild(this.Menu_mc);
      }
   }
}

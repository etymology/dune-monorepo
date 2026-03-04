//-----------------------------------------------------------------------------
// Uses:
//   Called when login button is pressed.
//-----------------------------------------------------------------------------
function login()
{
  // Fetch supplied password.
  var password = $( "#loginPassword" ).val()

  // Attempt to login.
  winder.login
  (
    password,
    function( loginResult )
    {
      // Did the login work?
      if ( loginResult )
      {
        // Reload.
        $( "#loginResult" )
          .html( "Reloading..." )
          .removeClass( "inError" )

        location.reload( true )
      }
      else
        // Signify there was a problem.
        $( "#loginResult" )
          .html( "Login incorrect." )
          .addClass( "inError" )
    }
  )

}


//-----------------------------------------------------------------------------
// Uses:
//   Called when page loads.
//-----------------------------------------------------------------------------
$( document ).ready
(
  function()
  {
    var clickCount = 0
    var timer

    // $$$TEMPORARY - Backdoor function.  Remove when login is functional.
    $( "#loginHeader" )
      .click
      (
        function()
        {
          clickCount += 1

          if ( clickCount >= 3 )
             $( "#loginPassword" ).val( "PSL#Winder" )

          if ( null == timer )
            timer = setTimeout
            (
              function()
              {
                timer = null
                clickCount = 0
              },
              500
            )
        }
      )
  }
)

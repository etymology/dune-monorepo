function Menu( modules )
{
  //-----------------------------------------------------------------------------
  //-----------------------------------------------------------------------------
  function toggleFullscreen()
  {
    var isFullScreen =
      (
        document.fullscreenElement
        || document.mozFullScreenElement
        || document.webkitFullscreenElement
      )

    if ( ! isFullScreen )
    {
      var element = document.documentElement
      if ( element.requestFullscreen )
        element.requestFullscreen()
      else
      if ( element.mozRequestFullScreen )
        element.mozRequestFullScreen()
      else
      if ( element.webkitRequestFullscreen )
        element.webkitRequestFullscreen()
      else
      if ( element.msRequestFullscreen )
        element.msRequestFullscreen()
    }
    else
    {
      if ( document.exitFullscreen )
        document.exitFullscreen()
      else
      if ( document.mozCancelFullScreen )
        document.mozCancelFullScreen()
      else
      if ( document.webkitExitFullscreen )
        document.webkitExitFullscreen()
    }

  }

  window[ "Menu" ] = this

}
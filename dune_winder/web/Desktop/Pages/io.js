function IO( modules )
{
  var winder = modules.get( "Winder" )

  //-----------------------------------------------------------------------------
  // Uses:
  //   Load an I/O query into a table.
  // Input:
  //   listRequest - Request to load list of I/O.
  //   itemRequestBuilder - Callback to build request for each I/O point.
  //   tag - Tag to place I/O list after loading.
  //-----------------------------------------------------------------------------
  function loadIO_Set( listRequest, itemRequestBuilder, tag )
  {
    winder.call
    (
      listRequest.name,
      listRequest.args || {},
      function( response )
      {
        if ( ! response || ! response.ok || ! response.data )
          return

        var data = response.data
        var columnNames = [ "Name", "Value" ]
        var widths = [ "60%", "40%" ]
        var filteredTable = new FilteredTable( columnNames, false, widths )

        filteredTable.loadFromArray( data )
        filteredTable.display( tag )

        for ( var row in data )
        {
          var ioPoint = data[ row ]
          var name = ioPoint[ 0 ]
          var request = itemRequestBuilder( name )

          let localRow = row

          // Update function.
          winder.addPeriodicCallback
          (
            request,
            function( data )
            {
              // Get the cell id this data is stored.
              let id = filteredTable.getCellId( localRow, 1 )

              // If this cell exists...
              if ( id )
                $( "#" + id ).html( data )
            }
          )
        }
      }
    )
  }

  //-----------------------------------------------------------------------------
  // Uses:
  //   Load all I/O.
  //-----------------------------------------------------------------------------
  function loadIO()
  {
    var commands = window.CommandCatalog
    loadIO_Set
    (
      { name: commands.lowLevelIO.getInputs, args: {} },
      function( name ) { return { name: commands.lowLevelIO.getInput, args: { name: name } } },
      "#inputsDiv"
    )
    loadIO_Set
    (
      { name: commands.lowLevelIO.getOutputs, args: {} },
      function( name ) { return { name: commands.lowLevelIO.getOutput, args: { name: name } } },
      "#outputsDiv"
    )
    loadIO_Set
    (
      { name: commands.lowLevelIO.getTags, args: {} },
      function( name ) { return { name: commands.lowLevelIO.getTag, args: { name: name } } },
      "#tagsDiv"
    )
  }

  // Load I/O lists and have this function run after error recovery.
  loadIO()
  winder.addErrorClearCallback( loadIO )

  // //-----------------------------------------------------------------------------
  // // Uses:
  // //   Called when page loads.
  // //-----------------------------------------------------------------------------
  // $( document ).ready
  // (
  //   function()
  //   {
  //     // Load I/O lists and have this function run after error recovery.
  //     loadIO()
  //     winder.addErrorClearCallback( loadIO )
  //   }
  // )

  window[ "io" ] = this
}
